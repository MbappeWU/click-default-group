# -*- coding: utf-8 -*-
import click
from click.testing import CliRunner
import pytest

from click_default_group import DefaultGroup


@click.group(cls=DefaultGroup, default='foo', invoke_without_command=True)
@click.option('--group-only', is_flag=True)
def cli(group_only):
    # Called if invoke_without_command=True.
    if group_only:
        click.echo('--group-only passed.')


@cli.command()
@click.option('--foo', default='foo')
def foo(foo):
    click.echo(foo)


@cli.command()
def bar():
    click.echo('bar')


r = CliRunner()


def test_default_command_with_arguments():
    assert r.invoke(cli, ['--foo', 'foooo']).output == 'foooo\n'
    assert 'no such option' in r.invoke(cli, ['-x']).output.lower()


def test_group_arguments():
    assert r.invoke(cli, ['--group-only']).output == '--group-only passed.\n'


def test_explicit_command():
    assert r.invoke(cli, ['foo']).output == 'foo\n'
    assert r.invoke(cli, ['bar']).output == 'bar\n'


def test_set_ignore_unknown_options_to_false():
    with pytest.raises(ValueError):
        DefaultGroup(ignore_unknown_options=False)


def test_default_if_no_args():
    cli = DefaultGroup()

    @cli.command()
    @click.argument('foo', required=False)
    @click.option('--bar')
    def foobar(foo, bar):
        click.echo(foo)
        click.echo(bar)

    cli.set_default_command(foobar)
    assert r.invoke(cli, []).output.startswith('Usage:')
    assert r.invoke(cli, ['foo']).output == 'foo\n\n'
    assert r.invoke(cli, ['foo', '--bar', 'bar']).output == 'foo\nbar\n'
    cli.default_if_no_args = True
    assert r.invoke(cli, []).output == '\n\n'


def test_format_commands():
    help = r.invoke(cli, ['--help']).output
    assert 'foo*' in help
    assert 'bar*' not in help
    assert 'bar' in help


def test_deprecation():
    # @cli.command(default=True) has been deprecated since 1.2.
    cli = DefaultGroup()
    pytest.deprecated_call(cli.command, default=True)


@click.group(cls=DefaultGroup, default='baz', invoke_without_command=True)
@click.option('--group-value')
def cli_with_separator(group_value):
    if group_value is not None:
        click.echo('group-value: {}'.format(group_value))


@cli_with_separator.command()
@click.argument('argument', nargs=-1)
@click.option('--option')
def baz(argument, option):
    argument = argument[0] if len(argument) == 1 else repr(argument)
    click.echo('baz: argument: {}, option: {}'.format(argument, option))


def test_default_command_forwards_group_separator():
    result = r.invoke(cli_with_separator, ['--', '--starts-with-hyphens'])
    assert result.exit_code == 0
    assert result.output == 'baz: argument: --starts-with-hyphens, option: None\n'


def test_group_option_value_double_dash_is_data():
    result = r.invoke(cli_with_separator, ['--group-value', '--', 'argument'])
    assert result.exit_code == 0
    assert result.output == (
        'group-value: --\n'
        'baz: argument: argument, option: None\n'
    )


def test_existing_default_command_separator_position_is_preserved():
    result = r.invoke(
        cli_with_separator,
        ['argument', '--', '--starts-with-hyphens'],
    )
    assert result.exit_code == 0
    assert result.output == "baz: argument: ('argument', '--starts-with-hyphens'), option: None\n"


def test_explicit_command_after_group_separator_is_not_defaulted():
    result = r.invoke(cli_with_separator, ['--', 'baz', 'argument'])
    assert result.exit_code == 0
    assert result.output == 'baz: argument: argument, option: None\n'


def _counterexample_cli(root_default=None):
    callback_values = []

    def convert_root_value(ctx, param, value):
        callback_values.append(value)
        return value.upper() if value is not None else value

    @click.group(cls=DefaultGroup, default='show')
    @click.option(
        '--root-value',
        default=root_default,
        callback=convert_root_value,
    )
    def counterexample_cli(root_value):
        pass

    @counterexample_cli.command()
    @click.option('--child-flag', is_flag=True)
    @click.argument('words', nargs=-1)
    def show(child_flag, words):
        click.echo(repr((child_flag, words)))

    return counterexample_cli, callback_values


def test_counterexample_child_options_before_separator_match_explicit():
    cli_default, _ = _counterexample_cli()
    cli_explicit, _ = _counterexample_cli()
    default = r.invoke(cli_default, ['--child-flag', '--', '--literal'])
    explicit = r.invoke(
        cli_explicit,
        ['show', '--child-flag', '--', '--literal'],
    )
    assert (default.exit_code, default.output) == (
        explicit.exit_code,
        explicit.output,
    )
    assert default.exit_code == 0


def test_counterexample_converted_root_value_does_not_move_separator():
    cli_default, default_values = _counterexample_cli()
    cli_explicit, explicit_values = _counterexample_cli()
    default = r.invoke(
        cli_default,
        ['--root-value', 'text', '--', '--literal'],
    )
    explicit = r.invoke(
        cli_explicit,
        ['--root-value', 'text', 'show', '--', '--literal'],
    )
    assert (default.exit_code, default.output) == (
        explicit.exit_code,
        explicit.output,
    )
    assert default.exit_code == 0
    assert default_values == ['text']
    assert explicit_values == ['text']


def test_counterexample_default_value_is_not_argv_separator():
    cli_default, default_values = _counterexample_cli(root_default='--')
    cli_explicit, explicit_values = _counterexample_cli(root_default='--')
    default = r.invoke(cli_default, ['--', '--literal'])
    explicit = r.invoke(cli_explicit, ['show', '--', '--literal'])
    assert (default.exit_code, default.output) == (
        explicit.exit_code,
        explicit.output,
    )
    assert default.exit_code == 0
    assert default_values == ['--']
    assert explicit_values == ['--']


def test_counterexample_second_separator_keeps_first_separator_position():
    cli_default, _ = _counterexample_cli()
    cli_explicit, _ = _counterexample_cli()
    default = r.invoke(cli_default, ['--', '--literal', '--', 'tail'])
    explicit = r.invoke(
        cli_explicit,
        ['show', '--', '--literal', '--', 'tail'],
    )
    assert (default.exit_code, default.output) == (
        explicit.exit_code,
        explicit.output,
    )
    assert default.exit_code == 0


@pytest.mark.parametrize('args, remaining, error', [
    (['--', 'data'], ['data'], None),
    (['--number', 'invalid', '--', 'data'], ['data'], click.BadParameter),
    (['--pair', 'one'], ['one'], click.BadOptionUsage),
])
def test_caller_argv_keeps_native_consumption(args, remaining, error):
    @click.group(cls=DefaultGroup)
    @click.option('--number', type=int)
    @click.option('--pair', nargs=2)
    def group(number, pair):
        pass

    ctx = click.Context(group)
    try:
        if error is None:
            group.parse_args(ctx, args)
        else:
            with pytest.raises(error):
                group.parse_args(ctx, args)
        assert args == remaining
        assert all(type(arg) is str for arg in args)
    finally:
        ctx.close()


def test_converted_root_separator_value_keeps_child_options():
    seen = []

    def convert(ctx, param, value):
        seen.append((type(value), value))
        return 'converted'

    @click.group(cls=DefaultGroup, default='show')
    @click.option('--value', type=click.UNPROCESSED, callback=convert)
    def group(value):
        pass

    @group.command()
    @click.option('--child-flag', is_flag=True)
    @click.argument('words', nargs=-1)
    def show(child_flag, words):
        click.echo(repr((child_flag, words)))

    result = r.invoke(group, ['--value', '--', '--child-flag', 'text'])
    assert result.exit_code == 0
    assert result.output == "(True, ('text',))\n"
    assert seen == [(str, '--')]


@pytest.mark.parametrize('default_args, explicit_args', [
    (['--pair', '--', 'x', '--', '--literal'],
     ['--pair', '--', 'x', 'show', '--', '--literal']),
    (['--pair', 'a', '--', '--', '--literal'],
     ['--pair', 'a', '--', 'show', '--', '--literal']),
    (['--pair', '--', 'x', '--pair', 'a', '--', '--', '--literal'],
     ['--pair', '--', 'x', '--pair', 'a', '--', 'show', '--', '--literal']),
])
def test_nested_option_values_keep_actual_separator(default_args, explicit_args):
    @click.group(cls=DefaultGroup, default='show')
    @click.option('--pair', multiple=True, nargs=2, type=click.UNPROCESSED)
    def group(pair):
        assert all(type(value) is str for values in pair for value in values)

    @group.command()
    @click.argument('words', nargs=-1)
    def show(words):
        click.echo(repr(words))

    actual = r.invoke(group, default_args)
    expected = r.invoke(group, explicit_args)
    assert actual.exit_code == expected.exit_code == 0
    assert actual.output == expected.output == "('--literal',)\n"


def test_unknown_child_option_before_separator_still_fails():
    group, _ = _counterexample_cli()
    actual = r.invoke(group, ['--unknown', '--', '--literal'])
    expected = r.invoke(group, ['show', '--unknown', '--', '--literal'])
    assert actual.exit_code == expected.exit_code == 2
    assert actual.output == expected.output
    assert 'no such option' in actual.output.lower()


def test_root_positional_consumption_keeps_child_separator():
    @click.group(cls=DefaultGroup, default='show')
    @click.argument('root_word')
    def group(root_word):
        assert root_word == '--'

    @group.command()
    @click.argument('words', nargs=-1)
    def show(words):
        click.echo(repr(words))

    actual = r.invoke(group, ['--', '--', '--literal'])
    expected = r.invoke(group, ['--', '--', 'show', '--', '--literal'])
    assert actual.exit_code == expected.exit_code == 0
    assert actual.output == expected.output == "('--literal',)\n"


def test_flag_value_identity_is_preserved_before_callback():
    marker = []
    marker.append(marker)
    seen = []

    def check_identity(ctx, param, value):
        seen.append(value is marker)
        return value

    @click.group(cls=DefaultGroup, default='show')
    @click.option('--marker', is_flag=True, flag_value=marker,
                  type=click.UNPROCESSED, callback=check_identity)
    def group(marker):
        pass

    @group.command()
    @click.argument('word')
    def show(word):
        click.echo(word)

    result = r.invoke(group, ['--marker', '--', '--literal'])
    assert result.exit_code == 0
    assert result.output == '--literal\n'
    assert seen == [True]


@pytest.mark.parametrize('default_args, explicit_args', [
    (['--value=--', '--', '--literal'],
     ['--value=--', 'show', '--', '--literal']),
    (['-r--', '--', '--literal'],
     ['-r--', 'show', '--', '--literal']),
    (['--VaLuE', '--', '--', '--literal'],
     ['--VaLuE', '--', 'show', '--', '--literal']),
    (['-vc', '--', '--literal'],
     ['-v', 'show', '-c', '--', '--literal']),
])
def test_native_option_grammar_is_preserved(default_args, explicit_args):
    @click.group(cls=DefaultGroup, default='show', context_settings={
        'token_normalize_func': lambda token: token.lower(),
    })
    @click.option('-r', '--value')
    @click.option('-v', '--verbose', is_flag=True)
    def group(value, verbose):
        pass

    @group.command()
    @click.option('-c', '--child-flag', is_flag=True)
    @click.argument('words', nargs=-1)
    @click.pass_context
    def show(ctx, child_flag, words):
        click.echo(repr((ctx.parent.params, child_flag, words)))

    actual = r.invoke(group, default_args)
    expected = r.invoke(group, explicit_args)
    assert actual.exit_code == expected.exit_code == 0
    assert actual.output == expected.output


def test_resilient_parsing_keeps_original_argument_types():
    group, _ = _counterexample_cli()
    argv = ['--', '--literal']
    ctx = click.Context(group, resilient_parsing=True)
    try:
        group.parse_args(ctx, argv)
        name, command, args = group.resolve_command(ctx, list(argv))
        assert name == 'show'
        assert command is group.commands['show']
        assert argv == ['--literal']
        assert args == ['--', '--literal']
        assert all(type(arg) is str for arg in argv + args)
    finally:
        ctx.close()


def test_named_chain_commands_after_group_separator_are_unchanged():
    @click.group(cls=DefaultGroup, default='first', chain=True)
    def group():
        pass

    @group.command()
    @click.argument('word')
    def first(word):
        click.echo('first: ' + word)

    @group.command()
    def second():
        click.echo('second')

    actual = r.invoke(group, ['--', 'first', '--', '--literal', 'second'])
    expected = r.invoke(group, ['first', '--', '--literal', 'second'])
    assert actual.exit_code == expected.exit_code == 0
    assert actual.output == expected.output == 'first: --literal\nsecond\n'


if __name__ == '__main__':
    cli()
