"""One CLI surface; Isaac-only operations execute in an explicit Python runtime."""
import argparse
import importlib
import subprocess
import sys


def _runtime(module, arguments, python):
    # Never resolve the interpreter symlink: that can discard its venv context.
    return subprocess.call([python or sys.executable, '-m', module, *arguments])


def prepare(argv=None):
    parser = argparse.ArgumentParser(add_help=False, description='Prepare a frozen model: export in EA, then convert and audit in Isaac Python.')
    parser.add_argument('stage', choices=['export', 'convert', 'audit'])
    parser.add_argument('--python', help='Isaac Python executable for convert/audit; default current interpreter')
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments in (['--help'], ['-h']):
        parser.print_help()
        return
    args, rest = parser.parse_known_args(arguments)
    if args.stage == 'export':
        if args.python:
            parser.error('export uses the current EA environment; --python is for convert/audit')
        from tools.isaac.export import main
        return main(rest)
    return _runtime('environment.isaac.'+args.stage, rest, args.python)


def run(argv=None):
    parser = argparse.ArgumentParser(add_help=False, description='Run a pilot, one trial batch, or a multi-GPU campaign.')
    parser.add_argument('mode', choices=['pilot', 'batch', 'campaign'])
    parser.add_argument('--python', help='Isaac Python executable (required for campaign)')
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments in (['--help'], ['-h']):
        parser.print_help()
        return
    args, rest = parser.parse_known_args(arguments)
    if args.mode == 'campaign':
        if not args.python and not any(a in rest for a in ('--help', '-h')):
            parser.error('campaign requires --python pointing to Isaac Python')
        from scenario.balancing_cube.isaac_campaign import main
        return main((['--python', args.python] if args.python else [])+rest)
    return _runtime('environment.isaac.'+args.mode, rest, args.python)


def dispatch(action, argv):
    if action in ('prepare', 'run'):
        return globals()[action](argv)
    module = {'analyze': 'scenario.balancing_cube.isaac_analysis',
              'plot': 'tools.isaac.plots',
              'propose': 'scenario.balancing_cube.isaac_proposal'}[action]
    return importlib.import_module(module).main(argv)
