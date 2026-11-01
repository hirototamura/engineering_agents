"""Install the shared engineering catalog for an agent without clobbering edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from environment.engineering_analysis.catalog import SKILLS, validate_graph


def _install(repo, destination, previous_path, receipt_fields):
    repo = Path(repo).resolve()
    destination = Path(destination).expanduser().absolute()
    if any(parent.is_symlink() for parent in (destination, *destination.parents)):
        raise FileExistsError('Skill destination traverses a symlink')
    source = repo/'skills/engineering'
    if destination.resolve().is_relative_to(source.resolve()):
        raise ValueError('Skill destination must not be inside the source catalog')
    folders = sorted(p for p in source.iterdir() if (p/'SKILL.md').is_file())
    if not folders:
        raise ValueError('No versioned engineering skills found')
    validate_graph()
    if {p.name for p in folders} != set(SKILLS):
        raise ValueError('Skill folders and executable catalog disagree')
    for folder in folders:
        contract = json.loads((folder/'contract.json').read_text())
        if any(contract.get(k) != v for k,v in SKILLS[folder.name].contract().items()):
            raise ValueError('Skill contract differs from executable catalog: '+folder.name)
    if previous_path.is_symlink():
        raise FileExistsError('Refusing a symlink receipt')
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    planned = []
    hashes = {}
    for folder in folders:
        for path in folder.rglob('*'):
            if path.is_symlink():
                raise ValueError('Skill sources cannot contain symlinks')
            if not path.is_file():
                continue
            relative = path.relative_to(source)
            hashes[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
            target = destination/relative
            if target.is_symlink():
                raise FileExistsError(f'Refusing a symlink destination: {target}')
            if target.exists() and target.read_bytes() != path.read_bytes():
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if previous.get('skill_files', {}).get(str(relative)) != actual:
                    raise FileExistsError(f'Existing skill differs; review before updating: {target}')
            if any(parent.is_symlink() for parent in target.parents if parent != parent.parent):
                raise FileExistsError('Skill destination traverses a symlink')
            planned.append((path, target))
    obsolete = []
    for relative, expected in previous.get('skill_files', {}).items():
        if relative in hashes:
            continue
        target = destination/relative
        if not target.resolve().is_relative_to(destination.resolve()) or target.is_symlink():
            raise FileExistsError('Obsolete skill path escapes the installation')
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise FileExistsError('Obsolete skill has human edits; review before migration: '+relative)
            obsolete.append(target)
    for path, target in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != path.read_bytes():
            temporary = target.with_suffix(target.suffix+'.ea-install-tmp')
            if temporary.is_symlink():
                raise FileExistsError(f'Refusing a symlink temporary file: {temporary}')
            shutil.copyfile(path, temporary)
            temporary.replace(target)
    for target in obsolete:
        target.unlink()
    obsolete_dirs = {parent for target in obsolete for parent in target.parents
                     if parent != destination and parent.is_relative_to(destination)}
    for folder in sorted(obsolete_dirs, key=lambda p: len(p.parts), reverse=True):
        if folder.is_dir() and not folder.is_symlink() and not any(folder.iterdir()):
            folder.rmdir()
    tool_hashes = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for base in ('src/environment/engineering_analysis', 'src/tools/engineering_skills')
                   for p in (repo/base).glob('*.py')}
    receipt = {'schema_version':1, 'source_repository':str(repo), **receipt_fields,
               'skills':[p.name for p in folders], 'skill_files':hashes, 'tool_files':tool_hashes}
    previous_path.write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


def install(repo, home):
    """Hermes adapter: preserve its installed layout and receipt."""
    home = Path(home).expanduser().absolute()
    return _install(repo, home/'skills/engineering', home/'engineering-skills-install.json',
                    {'hermes_home': str(home)})


def install_catalog(repo, destination):
    """Install shared skill folders at an explicitly chosen agent destination."""
    destination = Path(destination).expanduser().absolute()
    return _install(repo, destination, destination/'.engineering-skills-install.json',
                    {'destination': str(destination)})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--destination', type=Path, help='Directory for the shared skill folders')
    target.add_argument('--hermes-home', type=Path, help='Use the existing Hermes layout')
    args=parser.parse_args()
    result = install(args.repo, args.hermes_home) if args.hermes_home else install_catalog(args.repo, args.destination)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
