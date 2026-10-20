"""Build an allowlisted platform bundle; private configuration is never included."""
import argparse
import io
import pathlib
import tarfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent


def package(target):
    sources = sorted((ROOT / 'arena').glob('*.py'))
    reporter = io.BytesIO()
    with zipfile.ZipFile(reporter, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source in sources:
            archive.writestr('arena/' + source.name, source.read_bytes())
        archive.writestr('README.txt', 'Python 3.11+. Follow your Spark Arena enrollment page. No GitHub or WeChat account required. Keep local configuration private.\n')
    with tarfile.open(target, 'w:gz') as archive:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o644
            archive.addfile(info, io.BytesIO(data))
        for source in sources:
            add('arena/' + source.name, source.read_bytes())
        for name in ('index.html', 'app.js', 'join.js', 'privacy.html', 'platform.css'):
            add('public/' + name, (ROOT / 'platform' / name).read_bytes())
        for name in ('logic.js', 'style.css'):
            add('public/' + name, (ROOT / 'web' / name).read_bytes())
        add('public/reporter.zip', reporter.getvalue())
        for name, source in [('service', 'spark-arena-platform.service.example'), ('nginx-locations', 'nginx-locations.conf.example')]:
            add(name, (ROOT / 'deploy/platform' / source).read_bytes())
    return pathlib.Path(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    print(package(parser.parse_args().output))
