"""Register the Isaac workflow without loading optional simulation packages."""
import typer


def register(app: typer.Typer) -> None:
    isaac = typer.Typer(help='Prepare, run and inspect Isaac cube experiments.', no_args_is_help=True)
    app.add_typer(isaac, name='isaac')
    descriptions = {
        'prepare': 'Export, convert or audit a frozen model.',
        'run': 'Run a pilot, batch or multi-GPU campaign.',
        'analyze': 'Screen a campaign or compare paired campaigns.',
        'plot': 'Plot pilot, trial or campaign telemetry.',
        'propose': 'Propose a bounded design from measured campaign evidence.',
    }
    for action, description in descriptions.items():
        def make_command(name):
            def entry(ctx: typer.Context):
                from tools.isaac.workflow import dispatch
                code = dispatch(name, list(ctx.args))
                if code:
                    raise typer.Exit(code)
            return entry
        isaac.command(action, help=description, context_settings={
            'allow_extra_args': True, 'ignore_unknown_options': True,
            'help_option_names': [],
        })(make_command(action))
