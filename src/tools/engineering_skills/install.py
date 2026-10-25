"""Install the four repository-owned skills into a Hermes profile without clobbering edits."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def install(repo, home):
    repo, home = Path(repo).resolve(), Path(home).expanduser().resolve()
    source = repo/'skills/engineering'
    folders = sorted(p for p in source.iterdir() if (p/'SKILL.md').is_file())
    if len(folders) != 4:
        raise ValueError('Expected four versioned engineering skills')
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
            target = home/'skills/engineering'/relative
            if target.is_symlink():
                raise FileExistsError(f'Refusing a symlink destination: {target}')
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise FileExistsError(f'Existing skill differs; review before updating: {target}')
            if any(parent.is_symlink() for parent in target.parents if parent != parent.parent):
                raise FileExistsError('Skill destination traverses a symlink')
            planned.append((path, target))
    for path, target in planned:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(path, target)
    tool_hashes = {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for base in ('src/environment/engineering_analysis', 'src/tools/engineering_skills')
                   for p in (repo/base).glob('*.py')}
    receipt = {'schema_version':1, 'source_repository':str(repo), 'hermes_home':str(home),
               'skills':[p.name for p in folders], 'skill_files':hashes, 'tool_files':tool_hashes}
    (home/'engineering-skills-install.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--hermes-home',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(install(args.repo,args.hermes_home),indent=2))

if __name__=='__main__':main()
