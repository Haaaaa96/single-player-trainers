"""Explicit read-only reconnect discovery using the current metadata layout.

Uses only the small reviewed metadata schema, never engine_game_types.json.
No value scan or remote execution, and never selects a PlayerModel candidate.
"""
import argparse
import json
from pathlib import Path
import probe
import uuid
from class_scan import candidate, scan_classes
from connection_diagnostics import ConnectionDiagnosticError
from runtime_metadata import resolve_runtime_specs, MetadataError
from release_info import VERSION
from runtime_paths import RESOURCE_ROOT, CACHE_ROOT
from game_install import validate_installation

HERE=Path(__file__).resolve().parent
REQUIRED=['Game.Model.PlayerModel','Game.Model.Player.Components.TalentPathModel',
          'Game.Model.Components.BagModel','Game.Model.Components.BagItemBase',
          'Game.Model.Components.BagItem','Game.Model.GameStoreManager']

def version_check(game_path):
    return validate_installation(game_path)

def validate_candidate(reader,klass,spec,meta):
    # Compatibility entry point used by config discovery.
    return candidate(reader, klass, spec, meta)[0]


def connect_discover(pid,max_resident_mib=None,max_seconds=120,progress=None,extra_types=(),*,expected_path=None):
    reviewed={x['name']:x for x in json.loads((RESOURCE_ROOT/'engine_runtime_handoff.json').read_text(encoding='utf-8-sig'))}
    names=list(dict.fromkeys(REQUIRED+list(extra_types)))
    missing=[name for name in names if name not in reviewed]
    if missing:raise RuntimeError('Missing reviewed type specifications: '+', '.join(missing))
    r=probe.Reader(pid,expected_path=expected_path)
    try:
        metadata=probe.verified_mappings(r)['metadata']
        if len(metadata)!=1:raise RuntimeError('Expected exactly one metadata 31 mapping')
        meta=metadata[0]['base']
        try:
            specs=resolve_runtime_specs(r,meta,reviewed,names)
        except MetadataError as error:
            raise ConnectionDiagnosticError('无法解析当前游戏的类型信息：'+str(error),
                {'stage':'metadata_resolution','reason':str(error)}) from error
        layout={'trainer_version':VERSION,'metadata_format':31,
                'relocated_types':[name for name in names if any(
                    specs[name][key]!=reviewed[name][key]
                    for key in ('nameFileOffset','typeDefinitionFileOffset','token','fieldCount'))]}
        try:
            found,diagnostic=scan_classes(r,meta,specs,max_mib=max_resident_mib,
                                         max_seconds=max_seconds,progress=progress)
        except ConnectionDiagnosticError as error:
            error.diagnostic.update(layout)
            raise
        diagnostic.update(layout)
        classes=[found[n] for n in names]
        # Final mapping and candidate checks stop a replacement/restart from
        # publishing addresses that belonged to a different metadata instance.
        if probe.verified_mappings(r)['metadata'][0]['base']!=meta:
            raise ConnectionDiagnosticError('扫描期间游戏元数据已变化，请重新连接。',
                {'stage':'discovery_recheck','reason':'metadata_mapping_changed'})
        for name in names:
            if not validate_candidate(r,int(found[name]['klass'],16),specs[name],meta):
                raise ConnectionDiagnosticError('扫描期间游戏类型已变化，请重新连接。',
                    {'stage':'discovery_recheck','type':name,'reason':'candidate_changed'})
        result=dict(pid=pid,executable_path=r.path,metadata_base=hex(meta),
                    scanned_bytes=diagnostic['read_bytes'],seconds=diagnostic['seconds'],
                    classes=classes,diagnostic=diagnostic)
        manager=found['Game.Model.GameStoreManager']
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        # Each cache file is atomic; the resolver still verifies every address.
        for name,data in [('classes.json',result),('objects.json',dict(pid=pid,managers=[manager]))]:
            temporary=CACHE_ROOT/(name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
                temporary.replace(CACHE_ROOT/name)
            finally:
                temporary.unlink(missing_ok=True)
        return result
    finally:r.close()

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--pid',type=int,required=True);ap.add_argument('--extra-type',action='append',default=[]);args=ap.parse_args()
    result=connect_discover(args.pid,extra_types=args.extra_type)
    print(json.dumps({'pid':result['pid'],'seconds':result['seconds'],'resident_bytes':result['scanned_bytes'],
                      'classes':[c['namespace']+'.'+c['name'] for c in result['classes']]},ensure_ascii=False,indent=2))
