"""Re-download the published third-party source archives and verify SHA256.

Python 3.11+ standard library. No compilation, extraction, or game access.
MIT License: TOOL_LICENSE.txt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    destination = args.destination.resolve()
    first = json.loads((root / 'sources-lock.json').read_text(encoding='utf8'))
    second = json.loads((root / 'nested-lock.json').read_text(encoding='utf8'))
    records = first['components'] + second['components'] + second['npm'] + second['go']
    hosts = {'codeload.github.com', 'proxy.golang.org', 'registry.npmjs.org'}
    for record in records:
        url = urllib.parse.urlsplit(record['archive_url'])
        if url.scheme != 'https' or url.hostname not in hosts:
            raise ValueError('Unexpected upstream source URL')
        target = (destination / record['archive']).resolve()
        if not target.is_relative_to(destination) or target == destination:
            raise ValueError('Unsafe destination path')
        expected = record['archive_sha256']
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                raise ValueError('Existing file differs; retain it and select another destination: ' + str(target))
            print('verified ' + record['archive'])
            continue
        request = urllib.request.Request(record['archive_url'], headers={'User-Agent': 'WorldApartTrainer-sources/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Downloaded archive hash differs: ' + record['name'])
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(data)
        print('downloaded ' + record['archive'])


if __name__ == '__main__':
    main()
