# -*- coding: utf-8 -*-
import inspect
import os
import subprocess
import sys
import threading

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
    assert result.output == (
        'baz: argument: --starts-with-hyphens, option: None\n')


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
    assert result.output == (
        "baz: argument: ('argument', '--starts-with-hyphens'), "
        "option: None\n")


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
def test_nested_option_values_keep_actual_separator(
    default_args, explicit_args
):
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


@click.group(cls=DefaultGroup, default='take', chain=True)
def chain_cli():
    pass


@chain_cli.command()
@click.argument('value')
def take(value):
    click.echo('take:{}'.format(value))
    return value


@chain_cli.command()
def show():
    click.echo('show')
    return 'show'


@pytest.mark.parametrize('args, output', [
    (['one', 'two'], 'take:one\ntake:two\n'),
    (['one', 'show'], 'take:one\nshow\n'),
    (['one', 'take', 'two'], 'take:one\ntake:two\n'),
    (['show', 'one', 'show', 'two'], 'show\ntake:one\nshow\ntake:two\n'),
    (['take', 'one', 'take', 'two'], 'take:one\ntake:two\n'),
    (['show', 'show'], 'show\nshow\n'),
    (['', 'two'], 'take:\ntake:two\n'),
    (['--', 'one', 'show', 'two'], 'take:one\nshow\ntake:two\n'),
])
def test_chain_default_progress_and_explicit_commands(args, output):
    result = r.invoke(chain_cli, args)
    assert result.exit_code == 0
    assert result.output == output


@click.group(cls=DefaultGroup, default='options', chain=True)
def option_chain_cli():
    pass


@option_chain_cli.command()
@click.option('--value')
def options(value):
    click.echo('value:{}'.format(value))


@option_chain_cli.command()
def done():
    click.echo('done')


@pytest.mark.parametrize('args, output', [
    (['--value', 'first', 'done'], 'value:first\ndone\n'),
    (['--value', 'first', 'done', 'options', '--value', 'second'],
     'value:first\ndone\nvalue:second\n'),
    (['options', '--value', 'first', 'options', '--value', 'second'],
     'value:first\nvalue:second\n'),
])
def test_chain_option_only_default_can_consume_arguments(args, output):
    result = r.invoke(option_chain_cli, args)
    assert result.exit_code == 0
    assert result.output == output


def test_chain_known_command_still_rejects_unknown_options():
    result = r.invoke(
        option_chain_cli, ['--value', 'first', 'done', '--value', 'second'])
    assert result.exit_code == 2
    assert 'no such option' in result.output.lower()
    assert 'value:first' not in result.output


def test_chain_default_option_error_and_help():
    result = r.invoke(option_chain_cli, ['--invalid'])
    assert result.exit_code == 2
    assert 'no such option' in result.output.lower()
    result = r.invoke(option_chain_cli, ['options', '--help'])
    assert result.exit_code == 0
    assert '--value' in result.output
    assert 'value:None' not in result.output


def test_chain_context_parse_reuse():
    ctx = click.Context(chain_cli)
    for value in ['same', 'same']:
        chain_cli.parse_args(ctx, [value])
        assert chain_cli.invoke(ctx) == [value]


def test_chain_direct_resolution_is_idempotent():
    ctx = click.Context(chain_cli)
    for unused in range(2):
        name, command, args = chain_cli.resolve_command(ctx, ['one'])
        assert name == 'take'
        assert command is chain_cli.commands['take']
        assert args == ['one']
    name, command, args = chain_cli.resolve_command(ctx, ['show'])
    assert name == 'show'
    assert args == []


@pytest.mark.parametrize('default', [None, 'absent'])
def test_resilient_missing_default_does_not_access_command_name(default):
    group = DefaultGroup(chain=True, default=default)
    ctx = click.Context(group, resilient_parsing=True)
    control = click.Group()
    control_ctx = click.Context(control, resilient_parsing=True)
    try:
        expected = control.resolve_command(control_ctx, ['missing'])
    except click.UsageError as expected_error:
        with pytest.raises(click.UsageError) as actual_error:
            group.resolve_command(ctx, ['missing'])
        assert actual_error.value.message == expected_error.message
    else:
        assert group.resolve_command(ctx, ['missing']) == expected


def test_resilient_no_progress_returns_parent_stop_signal():
    group = DefaultGroup(chain=True, default='zero')
    group.add_command(click.Command('zero'))
    ctx = click.Context(group, resilient_parsing=True)
    first = group.resolve_command(ctx, ['unknown'])
    assert first[1] is group.commands['zero']
    second = group.resolve_command(ctx, ['unknown'])
    assert second == (None, None, ['unknown'])


def test_resolution_failure_does_not_replay_unknown_token():
    group = DefaultGroup(chain=True, default='absent')
    group.add_command(click.Command('known'))
    ctx = click.Context(group)
    group.parse_args(ctx, ['--', 'missing'])
    with pytest.raises(click.UsageError):
        group.resolve_command(ctx, ['missing'])
    name, command, args = group.resolve_command(ctx, ['known'])
    assert name == 'known'
    assert command is group.commands['known']
    assert args == []


def test_token_normalization_lookup_keeps_latest_resolution_state():
    group = DefaultGroup(default=None)
    group.add_command(click.Command('known'))
    ctx = click.Context(
        group, token_normalize_func=lambda value: value.lower())
    name, command, args = group.resolve_command(ctx, ['KNOWN'])
    assert name == 'known'
    assert command is group.commands['known']
    assert args == []


def _run_chain_child(script, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    source_dir = os.path.dirname(inspect.getfile(DefaultGroup))
    env['PYTHONPATH'] = source_dir + os.pathsep + env.get('PYTHONPATH', '')
    child = subprocess.Popen(
        [sys.executable, '-c', script], cwd=source_dir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    expired = []

    def stop_child():
        expired.append(True)
        try:
            child.kill()
        except OSError:
            pass

    deadline = threading.Timer(5, stop_child)
    deadline.start()
    try:
        stdout, stderr = child.communicate()
    finally:
        deadline.cancel()
        deadline.join()
    return (
        child.returncode, stdout.decode('utf-8'), stderr.decode('utf-8'),
        bool(expired),
    )


_ZERO_CHAIN_PROGRAM = """
import click
from click_default_group import DefaultGroup
@click.group(
    cls=DefaultGroup, default='zero', chain=True, default_if_no_args=True
)
def cli():
    click.echo('group')
@cli.command()
def zero():
    click.echo('default-callback')
@cli.command()
def known():
    click.echo('known')
cli(prog_name='cli', args=['unknown'])
"""


def test_chain_non_consuming_default_terminates_in_real_process():
    code, stdout, stderr, expired = _run_chain_child(_ZERO_CHAIN_PROGRAM)
    assert not expired
    assert code == 2
    assert stdout == 'group\n'
    assert 'Default command did not consume any arguments.' in stderr
    assert 'default-callback' not in stdout


def test_chain_zero_default_native_shell_completion_terminates():
    pytest.importorskip('click.shell_completion')
    script = _ZERO_CHAIN_PROGRAM.replace(
        "cli(prog_name='cli', args=['unknown'])", "cli(prog_name='cli')")
    code, stdout, stderr, expired = _run_chain_child(script, {
        '_CLI_COMPLETE': 'bash_complete',
        'COMP_WORDS': 'cli unknown k',
        'COMP_CWORD': '2',
    })
    assert not expired
    assert code == 0
    assert 'known' in stdout
    assert 'group' not in stdout
    assert not stderr


def test_group_callback_can_query_default_before_chain_parse():
    group = DefaultGroup(chain=True, default='take')
    events = []

    @click.pass_context
    def callback(ctx):
        name, command, args = group.resolve_command(ctx, ['one'])
        events.append(('peek', name, args))

    group.callback = callback

    @group.command()
    @click.argument('value')
    def take(value):
        events.append(('take', value))

    result = r.invoke(group, ['one'])
    assert result.exit_code == 0
    assert events == [('peek', 'take', ['one']), ('take', 'one')]


def test_group_callback_query_does_not_consume_native_separator():
    group = DefaultGroup(chain=True, default='take')
    values = []

    @click.pass_context
    def callback(ctx):
        group.resolve_command(ctx, ['query'])

    group.callback = callback

    @group.command()
    @click.argument('value')
    def take(value):
        values.append(value)

    result = r.invoke(group, ['--', '--literal'])
    assert result.exit_code == 0
    assert values == ['--literal']


def _set_result_callback(group, callback):
    if hasattr(group, '_result_callback'):
        group.result_callback()(callback)
    else:
        group.resultcallback()(callback)


def test_chain_callback_result_and_context_cleanup_order():
    group = DefaultGroup(chain=True, default='take')
    events = []

    @click.pass_context
    def callback(ctx):
        events.append(('group', ctx.invoked_subcommand))
        ctx.call_on_close(lambda: events.append(('close', 'root')))

    def register_close(ctx, param, value):
        events.append(('setup', value))
        ctx.call_on_close(lambda: events.append(('close', value)))
        return value

    group.callback = callback

    @group.command()
    @click.argument('value', callback=register_close)
    def take(value):
        events.append(('call', value))
        return value

    def finish(values):
        events.append(('result', values))
        return tuple(values)

    _set_result_callback(group, finish)
    assert group.main(
        args=['one', 'two'], standalone_mode=False) == ('one', 'two')
    assert events == [
        ('group', '*'), ('setup', 'one'), ('setup', 'two'),
        ('call', 'one'), ('close', 'one'),
        ('call', 'two'), ('close', 'two'),
        ('result', ['one', 'two']), ('close', 'root'),
    ]


def test_chain_stall_closes_pending_contexts_without_callbacks():
    script = """
import json
import click
from click_default_group import DefaultGroup
cli = DefaultGroup(chain=True, default='zero')
events = []
@click.pass_context
def callback(ctx):
    ctx.call_on_close(lambda: events.append('root'))
def register_close(ctx, param, value):
    ctx.call_on_close(lambda: events.append(value))
    return value
cli.callback = callback
@cli.command()
@click.argument('value', callback=register_close)
def take(value):
    events.append('take-callback')
@cli.command()
@click.option('--value', default='zero', callback=register_close)
def zero(value):
    events.append('zero-callback')
try:
    cli(prog_name='cli', args=['take', 'one', 'unknown'])
finally:
    print(json.dumps(events))
"""
    code, stdout, stderr, expired = _run_chain_child(script)
    assert not expired
    assert code == 2
    assert stdout.strip() == '["zero", "one", "root"]'


def test_chain_empty_invoke_uses_click_result_callback():
    group = DefaultGroup(chain=True, invoke_without_command=True)
    events = []
    group.callback = lambda: events.append('group')

    def finish(values):
        events.append(('result', values))
        return 'empty'

    _set_result_callback(group, finish)
    assert group.main(args=[], standalone_mode=False) == 'empty'
    assert events == ['group', ('result', [])]


def test_chain_resolution_queries_after_invoke_remain_idempotent():
    ctx = click.Context(chain_cli)
    chain_cli.parse_args(ctx, ['one'])
    assert chain_cli.invoke(ctx) == ['one']
    for unused in range(2):
        name, command, args = chain_cli.resolve_command(ctx, ['one'])
        assert name == 'take'
        assert args == ['one']


def test_chain_group_callback_args_match_click_and_allow_legacy_mutation():
    def invoke_group(group_type):
        group = group_type(chain=True)
        seen = []

        @click.pass_context
        def callback(ctx):
            seen.append(tuple(ctx.args))
            if ctx.args:
                ctx.args[-1] = 'changed'

        group.callback = callback

        @group.command()
        @click.argument('value')
        def take(value):
            return value

        returned = group.main(args=['take', 'one'], standalone_mode=False)
        return seen, returned

    assert invoke_group(DefaultGroup) == invoke_group(click.Group)


def test_chain_result_callback_is_looked_up_after_execution():
    group = DefaultGroup(chain=True, default='take')

    def callback():
        _set_result_callback(
            group, lambda values: 'changed-' + '-'.join(values))

    group.callback = callback

    @group.command()
    @click.argument('value')
    def take(value):
        return value

    assert group.main(args=['one'], standalone_mode=False) == 'changed-one'


@pytest.mark.parametrize('chain, allowed', [
    (True, True), (True, False), (False, True), (False, False),
])
def test_custom_invoke_wrapper_precedes_default_group(chain, allowed):
    events = []

    class GuardGroup(click.Group):
        def invoke(self, ctx):
            events.append('guard')
            if not allowed:
                ctx.fail('blocked')
            return super(GuardGroup, self).invoke(ctx)

    class CombinedGroup(GuardGroup, DefaultGroup):
        pass

    group = CombinedGroup(chain=chain, default='take')

    @group.command()
    @click.argument('value')
    def take(value):
        events.append(value)

    result = r.invoke(group, ['one'])
    if allowed:
        assert result.exit_code == 0
        assert events == ['guard', 'one']
    else:
        assert result.exit_code == 2
        assert events == ['guard']


def test_chain_does_not_silently_bypass_a_later_invoke_wrapper():
    events = []

    class GuardGroup(click.Group):
        def invoke(self, ctx):
            events.append('guard')
            ctx.fail('blocked')

    class CombinedGroup(DefaultGroup, GuardGroup):
        pass

    group = CombinedGroup(chain=True, default='take')

    @group.command()
    @click.argument('value')
    def take(value):
        events.append(value)

    result = r.invoke(group, ['one'])
    assert result.exit_code == 2
    assert 'Place custom invoke wrappers before DefaultGroup' in result.output
    assert not events
