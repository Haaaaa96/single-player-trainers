"""Current metadata identities for explicitly requested extension types.

Only class definitions are discovered. Live objects still come from the game's
canonical owners; no native code is invoked and no object candidate is selected.
"""
from runtime_metadata import RuntimeSpecs, RuntimeMetadataError
from class_scan import scan_classes, candidate
import struct

OWNERS = {
    '.Entry': ('System.Collections.Generic.Dictionary`2', 'mscorlib.dll'),
    '.Tables': ('System.Collections.Concurrent.ConcurrentDictionary`2', 'mscorlib.dll'),
    '.Node': ('System.Collections.Concurrent.ConcurrentDictionary`2', 'mscorlib.dll'),
    '.Slot': ('System.Collections.Generic.HashSet`1', 'System.Core.dll'),
    '.QuestSpecialStateOwner': ('Game.NpcLogicManager', 'Game.dll'),
    '.PlacementSettlementData': ('Game.UI.UPFLogic.Alchemy.UPFAlchemyPanel', 'Game.dll'),
    '.<>c__DisplayClass5_0': ('Game.MiniGamePersuadeCommand', 'Game.dll'),
    '.TimeScaleOverride': ('Game.GameTimeScaleController', 'Game.dll'),
}
EXTRA_IMAGES = {
    'Game.Singleton`1': 'A1Framework.dll',
    'SimpleSave.EntityID': 'SimpleSave.Runtime.dll',
    'SimpleSave.StoredEntity': 'SimpleSave.Runtime.dll',
    'SimpleSave.StoredEntityComponent': 'SimpleSave.Runtime.dll',
    'Emei.NotifiableList`1': 'EmeiClient.Runtime.dll',
    'A1.Flow.ProcContext': 'A1.Flow.Runtime.dll',
    'System.Collections.Generic.HashSet`1': 'System.Core.dll',
}


def reviewed(fullname, spec=None):
    spec = spec or {}
    owner, image = OWNERS.get(fullname, (None, None))
    image = spec.get('image_name', image or EXTRA_IMAGES.get(fullname))
    if image is None:
        if fullname.startswith(('Game.', 'LubanDatas.')):
            image = 'Game.dll'
        elif fullname.startswith('System.'):
            image = 'mscorlib.dll'
        elif fullname.startswith('Loxodon.'):
            image = 'Loxodon.Framework.dll'
        elif fullname.startswith('UnityEngine.'):
            image = 'UnityEngine.CoreModule.dll'
        else:
            raise RuntimeMetadataError('Unreviewed extension image: ' + fullname)
    result = dict(name=fullname, image_name=image,
                  fields=[dict(name=f['name']) for f in spec.get('fields', [])])
    if owner:
        result['declaring_type'] = owner
    return result


class ExtensionRuntime:
    def __init__(self, reader, metadata_base):
        self.reader, self.meta = reader, metadata_base
        self.specs = RuntimeSpecs(reader, metadata_base, [])
        self.classes = {}

    def spec(self, fullname, requirements=None):
        self.specs.register(reviewed(fullname, requirements))
        current = self.specs[fullname]
        return {**current,
                'type_definition_offset': current['typeDefinitionFileOffset'],
                'token': int(current['token'], 16),
                'field_count': current['fieldCount'],
                'fields': [{**f, 'token': int(f['token'], 16)} for f in current['all_fields']]}

    def class_address(self, fullname):
        self.spec(fullname)
        spec = self.specs[fullname]
        if fullname in self.classes:
            address = self.classes[fullname]
            if candidate(self.reader, address, spec, self.meta)[0] is None:
                raise RuntimeMetadataError('Cached extension class changed: ' + fullname)
            return address
        # Feature discovery can happen minutes after the base connection. Use
        # the current virtual regions, not the Reader's construction snapshot.
        regions = list(self.reader.iter_regions()) if hasattr(self.reader, 'iter_regions') else None
        found, _ = scan_classes(self.reader, self.meta, {fullname: spec}, regions=regions)
        address = int(found[fullname]['klass'], 16)
        self.classes[fullname] = address
        return address

    def owned_class_address(self, resolver, fullname):
        """Locate these live types through reviewed owners, without a heap scan.

        This is opt-in for the learning and aptitude readers. Unsupported root
        code keeps the existing validated discovery route; a changed owner on
        a supported route is rejected, never silently replaced by a heap hit.
        """
        from acquisition_context import _Context, CODE_PROFILES
        from write_guard import Refused
        if fullname not in ('Game.UIManager', 'Game.ConfigManager', 'LubanDatas.Tables'):
            raise Refused('类型不在管理器快捷定位范围内。')
        profiles = [profile for profile in CODE_PROFILES
                    if all(self.reader.read(resolver.module + rva, len(bytes.fromhex(expected))).hex() == expected
                           for rva, expected in profile['code'].items())]
        if not profiles:
            return self.class_address(fullname)
        if len(profiles) != 1:
            raise Refused('管理器入口代码不唯一。')
        context = _Context(resolver)
        main, _ = context.managers()
        mc = context.obj(main, 'Game.A1Main')
        listing = context.pointer(main + context.field(mc, '_managers', 0x15), 'owner.managers')
        lc = context.obj(listing, 'System.Collections.Generic.List`1')
        count = context.i(listing + context.field(lc, '_size', 8), 'owner.managers.size')
        context.i(listing + context.field(lc, '_version', 8), 'owner.managers.version')
        if not 1 <= count <= 128:
            raise Refused('管理器列表长度异常。')
        array = context.pointer(listing + context.field(lc, '_items', 0x1D), 'owner.managers.items')
        if not count <= context.q(array + 24, 'owner.managers.capacity') <= 256:
            raise Refused('管理器列表容量异常。')
        pointers = struct.unpack('<' + 'Q' * count,
                                 context.anchor(array + 32, count * 8, 'owner.managers.entries'))
        owner = 'Game.ConfigManager' if fullname == 'LubanDatas.Tables' else fullname
        matches = []
        for pointer in pointers:
            c = context.obj(pointer)
            if c['namespace'] + '.' + c['name'] == owner:
                matches.append((pointer, resolver.obj(pointer, owner)))
        if len(matches) != 1:
            raise Refused('所需管理器未就绪或不唯一：' + owner)
        pointer, c = matches[0]
        if fullname == 'LubanDatas.Tables':
            offset = resolver.field(c, '<Tables>k__BackingField', 0x12)
            pointer = resolver.q(pointer + offset, anchored=True)
            c = resolver.obj(pointer, fullname)
        klass = int(c['klass'], 16)
        self.spec(fullname)
        checked, reason = candidate(self.reader, klass, self.specs[fullname], self.meta)
        if checked is None:
            raise Refused('管理器类型身份校验失败：' + str(reason))
        context._finish_snapshot('读取期间管理器发生变化，请刷新。')
        resolver.anchors.extend((a['address'], a['expected_hex']) for a in context.anchors)
        return klass
