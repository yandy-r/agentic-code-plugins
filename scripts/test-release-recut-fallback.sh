#!/usr/bin/env bash
# Offline scratch-git regression for the destructive re-cut fallback in
# ycc/skills/releaser/references/release-ci-loop.md. Executes the exact
# recut-transaction block from the protocol against a temporary bare remote,
# with a stub gh (--cleanup-tag deletes the remote tag) and a stub publisher
# mirroring publish-release.sh --mode=create --confirm (remote tag must exist
# and peel to FIX_SHA). No network; no mutations outside the sandbox.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ROOT/ycc/skills/releaser/references/release-ci-loop.md"
python3 - "$ROOT" <<'PY'
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1])
text = (root / 'ycc/skills/releaser/references/release-ci-loop.md').read_text()
block = text.split('<!-- recut-transaction -->', 1)[1].split('```bash', 1)[1].split('```', 1)[0]
block = '\n'.join(line.removeprefix('   ') for line in block.splitlines())
env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
with tempfile.TemporaryDirectory(prefix='ycc-recut-') as tmp:
    base = Path(tmp)
    bin_dir = base / 'bin'
    bin_dir.mkdir()
    gh = bin_dir / 'gh'
    gh.write_text('''#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$CALLS"
[[ "$1 $2" == "release delete" && "$4 $5" == "--cleanup-tag --yes" ]]
[[ "${FAIL_STEP:-}" != delete ]]
git --git-dir="$REMOTE" update-ref -d "refs/tags/$3"
rm "$RELEASE_STATE"
''')
    publisher = bin_dir / 'publisher'
    publisher.write_text('''#!/usr/bin/env bash
set -euo pipefail
[[ "$3 $4" == "--mode=create --confirm" ]]
[[ -r "$2" && ! -e "$RELEASE_STATE" ]]
[[ "$(git cat-file -t "refs/tags/$1")" == tag ]]
[[ "$(git --git-dir="$REMOTE" rev-parse "refs/tags/$1^{commit}")" == "$FIX_SHA" ]]
printf 'publisher-verified-remote-tag\\n' >> "$CALLS"
[[ "${FAIL_STEP:-}" != publish ]]
printf published > "$RELEASE_STATE"
''')
    for file in (gh, publisher):
        file.chmod(0o755)
    transaction = base / 'transaction.sh'
    transaction.write_text(block)
    env['PATH'] = str(bin_dir) + os.pathsep + env['PATH']
    for case in ('success', 'preflight', 'delete', 'push', 'publish'):
        folder = base / case
        folder.mkdir()
        repo = folder / 'repo'
        remote = folder / 'remote.git'
        calls = folder / 'calls'
        release_state = folder / 'release'
        calls.touch()
        release_state.write_text('original release metadata')

        def git(*args, bare=False):
            return subprocess.check_output(
                ['git', *(['--git-dir=' + str(remote)] if bare else ['-C', str(repo)]), *args],
                env=env, text=True, stderr=subprocess.DEVNULL).strip()

        subprocess.run(['git', 'init', '-q', '--bare', str(remote)], env=env, check=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], env=env, check=True)
        git('config', 'user.name', 'ycc test')
        git('config', 'user.email', 'ycc-test@example.invalid')
        git('config', 'commit.gpgsign', 'false')
        git('config', 'tag.gpgsign', 'false')
        (repo / 'source').write_text('old\n')
        git('add', 'source')
        git('commit', '-qm', 'chore: initial fixture')
        old = git('rev-parse', 'HEAD')
        git('tag', '-a', 'v1.0.0', '-m', 'v1.0.0')
        old_tag = git('rev-parse', 'v1.0.0')
        git('remote', 'add', 'origin', str(remote))
        git('push', 'origin', 'HEAD:main', 'refs/tags/v1.0.0:refs/tags/v1.0.0')
        (repo / 'source').write_text('fix\n')
        git('commit', '-qam', 'fix: fixture validation')
        fix = git('rev-parse', 'HEAD')
        git('push', 'origin', 'HEAD:main')
        notes = folder / 'notes.md'
        notes.write_text('reviewed notes')
        if case == 'preflight':
            git('tag', '-d', 'v1.0.0')
            git('tag', '-a', 'v1.0.0', '-m', 'unexpected', fix)
        if case == 'push':
            hook = remote / 'hooks/pre-receive'
            hook.write_text('#!/usr/bin/env bash\nexit 1\n')
            hook.chmod(0o755)
        run_env = dict(env, TAG='v1.0.0', FIX_SHA=fix, RELEASED_SHA=old,
                       RELEASE_BRANCH='main', NOTES_PATH=str(notes), PUBLISHER=str(publisher),
                       REMOTE=str(remote), CALLS=str(calls), RELEASE_STATE=str(release_state),
                       FAIL_STEP=case)
        result = subprocess.run(['bash', str(transaction)], cwd=repo, env=run_env,
                                text=True, capture_output=True, timeout=30)
        trace = calls.read_text()
        if case == 'success':
            assert result.returncode == 0, result.stdout + result.stderr
            assert git('rev-parse', 'v1.0.0^{commit}', bare=True) == fix
            assert git('cat-file', '-t', 'v1.0.0', bare=True) == 'tag'
            assert release_state.read_text() == 'published'
            assert 'publisher-verified-remote-tag' in trace
        else:
            assert result.returncode != 0 and 'RESULT=loop-blocked' in result.stdout, result.stdout
            stage = {'preflight': 'preflight-local-mismatch', 'delete': 'delete',
                     'push': 'tag-push', 'publish': 'publish'}[case]
            assert 'RECOVERY_STEP=' + stage in result.stdout, result.stdout
            if case in ('preflight', 'delete'):
                assert git('rev-parse', 'v1.0.0', bare=True) == old_tag
                assert release_state.read_text() == 'original release metadata'
                assert 'publisher' not in trace
            if case == 'preflight':
                assert not trace
            if case == 'delete':
                assert git('rev-parse', 'v1.0.0') == old_tag
            if case == 'push':
                assert not release_state.exists()
                assert git('rev-parse', 'v1.0.0^{commit}') == fix
                assert 'publisher' not in trace
            if case == 'publish':
                assert git('rev-parse', 'v1.0.0^{commit}', bare=True) == fix
                assert not release_state.exists()
                assert 'publisher-verified-remote-tag' in trace
        print('[pass] scratch re-cut ' + case)
print('5 passed, 0 failed (no network; real git only inside temporary repos)')
PY
