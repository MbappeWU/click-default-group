"""
   click_default_group
   ~~~~~~~~~~~~~~~~~~~

   Define a default subcommand by `default=True`:

   .. sourcecode:: python

      import click
      from click_default_group import DefaultGroup

      @click.group(cls=DefaultGroup, default_if_no_args=True)
      def cli():
          pass

      @cli.command(default=True)
      def foo():
          click.echo('foo')

      @cli.command()
      def bar():
          click.echo('bar')

   Then you can invoke that without explicit subcommand name:

   .. sourcecode:: console

      $ cli.py --help
      Usage: cli.py [OPTIONS] COMMAND [ARGS]...

      Options:
        --help    Show this message and exit.

      Command:
        foo*
        bar

      $ cli.py
      foo
      $ cli.py foo
      foo
      $ cli.py bar
      bar

"""
from collections import deque
import warnings

import click


__all__ = ['DefaultGroup']
__version__ = '1.2.4'


class _DelimiterToken(str):
    """Observe Click's native delimiter branch without changing its parser."""

    __hash__ = str.__hash__

    def __new__(cls, value, observed_args):
        token = str.__new__(cls, value)
        token.original = value
        token.observed_args = observed_args
        token.native_remainder = None
        return token

    def __eq__(self, other):
        if other == '--' and self.native_remainder is None:
            self.native_remainder = list(self.observed_args)
        return str.__eq__(self, other)


def _restore_delimiter_tokens(value, seen=None):
    if type(value) is _DelimiterToken:
        return value.original
    if type(value) not in (list, tuple):
        return value
    if seen is None:
        seen = set()
    if id(value) in seen:
        return value
    seen.add(id(value))
    restored = [_restore_delimiter_tokens(item, seen) for item in value]
    if all(original is replacement
           for original, replacement in zip(value, restored)):
        return value
    return type(value)(restored)


class DefaultGroup(click.Group):
    """Invokes a subcommand marked with `default=True` if any subcommand not
    chosen.

    :param default_if_no_args: resolves to the default command if no arguments
                               passed.

    """

    def __init__(self, *args, **kwargs):
        # To resolve as the default command.
        if not kwargs.get('ignore_unknown_options', True):
            raise ValueError('Default group accepts unknown options')
        self.ignore_unknown_options = True
        self.default_cmd_name = kwargs.pop('default', None)
        self.default_if_no_args = kwargs.pop('default_if_no_args', False)
        super(DefaultGroup, self).__init__(*args, **kwargs)

    def set_default_command(self, command):
        """Sets a command function as the default command."""
        cmd_name = command.name
        self.add_command(command)
        self.default_cmd_name = cmd_name

    def parse_args(self, ctx, args):
        ctx._default_group_previous_remaining = None
        if not args and self.default_if_no_args:
            args.insert(0, self.default_cmd_name)
        return super(DefaultGroup, self).parse_args(ctx, args)

    def make_parser(self, ctx):
        parser = super(DefaultGroup, self).make_parser(ctx)
        native_parse_args = parser.parse_args

        def parse_args(args):
            ctx._default_group_separator_index = None
            observed_args = []
            delimiter_tokens = []
            for arg in args:
                if isinstance(arg, (str, type(u''))) and arg == '--':
                    token = _DelimiterToken(arg, observed_args)
                    delimiter_tokens.append(token)
                    observed_args.append(token)
                else:
                    observed_args.append(arg)

            try:
                opts, parsed_args, order = native_parse_args(observed_args)
            finally:
                args[:] = _restore_delimiter_tokens(observed_args)
            for name, value in list(opts.items()):
                opts[name] = _restore_delimiter_tokens(value)
            parsed_args[:] = _restore_delimiter_tokens(parsed_args)
            for arg in delimiter_tokens:
                if type(arg) is not _DelimiterToken:
                    continue
                if arg.native_remainder is not None:
                    remainder = [
                        _restore_delimiter_tokens(item)
                        for item in arg.native_remainder
                    ]
                    ctx._default_group_separator_index = max(
                        0, len(parsed_args) - len(remainder))
                    break

            return opts, parsed_args, order

        parser.parse_args = parse_args
        return parser

    def get_command(self, ctx, cmd_name):
        ctx.__dict__.pop('arg0', None)
        if cmd_name not in self.commands:
            # No command name matched.
            ctx.arg0 = cmd_name
            cmd_name = self.default_cmd_name
        return super(DefaultGroup, self).get_command(ctx, cmd_name)

    def resolve_command(self, ctx, args):
        ctx.__dict__.pop('arg0', None)
        position = getattr(ctx, '_default_group_separator_index', None)
        if ctx.resilient_parsing:
            ctx._default_group_separator_index = None
        if self.chain and ctx.resilient_parsing:
            remaining = tuple(args)
            previous = getattr(ctx, '_default_group_previous_remaining', None)
            if previous == remaining:
                if ctx.resilient_parsing:
                    return None, None, args
                ctx.fail('Default command did not consume any arguments.')
            ctx._default_group_previous_remaining = remaining
        base = super(DefaultGroup, self)
        try:
            cmd_name, cmd, args = base.resolve_command(ctx, args)
        finally:
            arg0 = ctx.__dict__.pop('arg0', None)
        if cmd is not None and arg0 is not None:
            args.insert(0, arg0)
            if position is not None:
                args.insert(position, '--')
            cmd_name = cmd.name
        return cmd_name, cmd, args

    def invoke(self, ctx):
        try:
            if not self.chain:
                return super(DefaultGroup, self).invoke(ctx)
            if hasattr(ctx, '_protected_args'):
                protected_name = '_protected_args'
            elif hasattr(ctx, 'protected_args'):
                protected_name = 'protected_args'
            else:
                protected_name = None
            args = ctx.args
            if protected_name is not None:
                args = list(getattr(ctx, protected_name)) + args
            if not args:
                return super(DefaultGroup, self).invoke(ctx)
            next_invoke = super(DefaultGroup, self).invoke
            next_function = getattr(
                next_invoke, '__func__',
                getattr(next_invoke, 'im_func', next_invoke))
            native_function = getattr(
                click.Group.invoke, '__func__',
                getattr(click.Group.invoke, 'im_func', click.Group.invoke))
            if next_function is not native_function:
                ctx.fail('Place custom invoke wrappers before DefaultGroup '
                         'in the class inheritance order.')
            if protected_name is not None:
                ctx.args = []
                setattr(ctx, protected_name, [])
            with ctx:
                ctx.invoked_subcommand = '*'
                click.Command.invoke(self, ctx)
                pending = deque()
                try:
                    while args:
                        before = tuple(args)
                        name, command, command_args = self.resolve_command(
                            ctx, args)
                        ctx._default_group_separator_index = None
                        child = command.make_context(
                            name, command_args, parent=ctx,
                            allow_extra_args=True,
                            allow_interspersed_args=False,
                        )
                        pending.append(child)
                        args, child.args = child.args, []
                        if tuple(args) == before:
                            ctx.fail(
                                'Default command did not consume '
                                'any arguments.')
                    results = []
                    while pending:
                        child = pending.popleft()
                        with child:
                            results.append(child.command.invoke(child))
                finally:
                    while pending:
                        pending.pop().close()
                if hasattr(self, '_result_callback'):
                    result_callback = self._result_callback
                else:
                    result_callback = self.result_callback
                if result_callback is not None:
                    return ctx.invoke(result_callback, results, **ctx.params)
                return results
        finally:
            ctx.__dict__.pop('arg0', None)
            ctx._default_group_separator_index = None
            ctx._default_group_previous_remaining = None

    def format_commands(self, ctx, formatter):
        formatter = DefaultCommandFormatter(self, formatter, mark='*')
        return super(DefaultGroup, self).format_commands(ctx, formatter)

    def command(self, *args, **kwargs):
        default = kwargs.pop('default', False)
        decorator = super(DefaultGroup, self).command(*args, **kwargs)
        if not default:
            return decorator
        warnings.warn('Use default param of DefaultGroup or '
                      'set_default_command() instead', DeprecationWarning)

        def _decorator(f):
            cmd = decorator(f)
            self.set_default_command(cmd)
            return cmd

        return _decorator


class DefaultCommandFormatter(object):
    """Wraps a formatter to mark a default command."""

    def __init__(self, group, formatter, mark='*'):
        self.group = group
        self.formatter = formatter
        self.mark = mark

    def __getattr__(self, attr):
        return getattr(self.formatter, attr)

    def write_dl(self, rows, *args, **kwargs):
        rows_ = []
        for cmd_name, help in rows:
            if cmd_name == self.group.default_cmd_name:
                rows_.insert(0, (cmd_name + self.mark, help))
            else:
                rows_.append((cmd_name, help))
        return self.formatter.write_dl(rows_, *args, **kwargs)
