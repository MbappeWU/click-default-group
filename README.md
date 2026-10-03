Click Default Group
===================

[![Build Status](https://github.com/click-contrib/click-default-group/actions/workflows/build.yaml/badge.svg)](https://github.com/click-contrib/click-default-group/actions/workflows/build.yaml)

`DefaultGroup` is a subclass of
[`click.Group`](https://click.pocoo.org/6/api/#click.Group).  But it invokes
the default subcommand instead of showing a help message when a subcommand is
not passed.

Usage
-----

Define a default subcommand by `default=NAME`:

```python
import click
from click_default_group import DefaultGroup

@click.group(cls=DefaultGroup, default='foo', default_if_no_args=True)
def cli():
    pass

@cli.command()
def foo():
    click.echo('foo')

@cli.command()
def bar():
    click.echo('bar')
```

Then you can invoke that without explicit subcommand name:

```console
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
```

Chained commands
----------------

With `chain=True`, an implicit default command can be used more than once when
it consumes arguments. For example, a default command that takes one argument
can handle `cli.py first second`, and can be mixed with explicit commands.
A default command that cannot consume an unknown token raises a usage error
instead of repeating indefinitely. Shell completion also stops safely on
that input. Group callbacks keep Click's normal execution order; an invalid
chain does not execute its subcommand callbacks.

An option-only default can consume its options before the next command.
After an explicit command, use the next command's name to separate its options
from the previous command's options, as required by Click's chain parser.

If combining `DefaultGroup` with another group class that overrides `invoke`,
put that wrapper class before `DefaultGroup` in the inheritance order. A
non-empty chain rejects the opposite order rather than silently skipping the
wrapper. Ordinary subclasses overriding `invoke` and calling `super` work
normally.

Compatibility
-------------

`click-default-group` is compatible with these Click versions:

- Click-8.x
- Click-7.x
- Click-6.x
- Click-5.x
- Click-4.x

Licensing
---------

Written by [Heungsub Lee], and distributed under the [BSD 3-Clause] license.

[Heungsub Lee]: https://subl.ee/
[BSD 3-Clause]: https://opensource.org/licenses/BSD-3-Clause
