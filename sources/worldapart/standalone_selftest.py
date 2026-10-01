"""Offline smoke test of the exact frozen artifact. Never opens a game handle."""
import ctypes
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback


# Independent release expectations. Do not derive these from the embedded
# manifest: a consistently incomplete manifest must not make a broken EXE pass.
EXPECTED_ADDITIONAL_MODULES = frozenset((
    'meridian_adapter', 'meridian_logic', 'meridian_oneclick', 'meridian_ui', 'meridian_write',
    'character_attributes', 'character_attributes_native', 'character_attributes_write', 'character_ui',
    'character_attributes_interact', 'character_attributes_interact_native', 'character_attributes_interact_write',
    'current_resources', 'current_resources_native', 'current_resources_ui',
    'character_profile', 'character_profile_ui', 'character_lifespan', 'character_lifespan_native', 'character_lifespan_ui',
    'game_speed', 'game_speed_native', 'game_speed_ui', 'navigation',
    'native_broker', 'native_broker_host', 'native_scalar_guard', 'game_connection', 'item_categories',
    'extension_runtime', 'native_method_profiles', 'audit_update_readonly',
    'alchemy_adapter', 'alchemy_context', 'alchemy_talents', 'alchemy_ui', 'alchemy_recipe', 'alchemy_recipe_ui',
    'crafting_adapter', 'crafting_logic', 'crafting_talents', 'crafting_ui',
    'dual_cultivation_common', 'dual_cultivation_native', 'dual_cultivation_adapter',
    'dual_cultivation_ui', 'jade_adapter', 'jade_ui',
    'photostone_logic', 'photostone_adapter', 'photostone_native', 'photostone_ui', 'photostone_concurrent',
    'persuasion_adapter', 'persuasion_context', 'persuasion_native', 'persuasion_ui'))
EXPECTED_CORE_MODULES = frozenset((
    'app', 'game_adapter', 'game_install', 'probe', 'resolver', 'discovery', 'config_probe',
    'runtime_metadata', 'class_scan', 'connection_diagnostics',
    'acquisition_adapter', 'acquisition_catalog', 'acquisition_context', 'acquisition_existing', 'acquisition_ui',
    'native_acquisition_session', 'native_write', 'learning_adapter', 'learning_write', 'learning_completion',
    'learning_ui', 'runtime_paths', 'release_info', 'write_guard', 'ui_errors',
    'standalone_selftest', 'standalone_lifetime_selftest'))
EXPECTED_RESOURCES = frozenset((
    'engine_runtime_handoff.json', 'acquisition_context_specs.json', 'acquisition_bridge.js',
    'RELEASE_NOTES.md', 'THIRD_PARTY_NOTICES.md', 'meridian_specs.json',
    'character_attributes_specs.json', 'character_attributes_interact_specs.json', 'current_resources_specs.json',
    'character_lifespan_specs.json', 'game_speed_specs.json', 'alchemy_specs.json', 'alchemy_recipe_specs.json',
    'crafting_specs.json', 'dual_cultivation_specs.json', 'jade_specs.json',
    'photostone_specs.json', 'photostone_catalog.json', 'persuasion_specs.json', 'native_method_evidence.json'))
EXPECTED_TABS = ('角色点数', '背包数量', '人物属性', '资质与技艺', '修行储备', '增加寿元', '当前资源',
                 '添加物品与秘籍', '功法学习小游戏', '疏经导脉辅助', '游戏速度',
                 '留影石', '秒说服', '炼丹辅助', '丹方探索', '炼器辅助', '双修', '刮玉')
EXPECTED_NAVIGATION = {
    '角色': ('角色点数', '人物属性', '资质与技艺', '修行储备', '增加寿元'),
    '背包与资源': ('背包数量', '添加物品与秘籍', '当前资源'),
    '游戏辅助': ('功法学习小游戏', '疏经导脉辅助', '游戏速度', '留影石', '秒说服'),
    '生活技艺': ('炼丹辅助', '丹方探索', '炼器辅助', '双修', '刮玉'),
}


def _require_exact_set(label, actual, expected):
    missing, extra = sorted(expected - set(actual)), sorted(set(actual) - expected)
    if missing or extra:
        raise RuntimeError(f'{label}: missing={missing}; extra={extra}')


def validate_bundle_manifest(manifest):
    if (not isinstance(manifest, dict) or type(manifest.get('format')) is not int or manifest['format'] != 1
            or set(manifest) != {'format', 'additional_modules', 'resources'}):
        raise RuntimeError('Invalid bundle manifest schema or format.')
    modules, resources = manifest['additional_modules'], manifest['resources']
    if not isinstance(modules, list) or any(not isinstance(name, str) for name in modules):
        raise RuntimeError('Invalid additional module list.')
    if len(modules) != len(set(modules)):
        raise RuntimeError('Duplicate additional modules in bundle manifest.')
    _require_exact_set('Bundle manifest modules', modules, EXPECTED_ADDITIONAL_MODULES)
    if not isinstance(resources, dict) or any(not isinstance(name, str) for name in resources):
        raise RuntimeError('Invalid resource map.')
    _require_exact_set('Bundle manifest resources', resources, EXPECTED_RESOURCES)
    if any(not isinstance(digest, str) or len(digest) != 64
           or any(c not in '0123456789abcdef' for c in digest) for digest in resources.values()):
        raise RuntimeError('Invalid resource SHA-256 in bundle manifest.')


def validate_release_ui(tabs, version, introduction):
    if list(tabs) != list(EXPECTED_TABS):
        raise RuntimeError(f'Release tabs differ: expected={list(EXPECTED_TABS)}; actual={list(tabs)}')
    if (not isinstance(version, str) or not version or not isinstance(introduction, str)
            or not introduction.splitlines() or version not in introduction.splitlines()[0]):
        raise RuntimeError('Feature introduction does not identify this release version.')


def validate_release_navigation(groups):
    if (list(groups) != list(EXPECTED_NAVIGATION) or
            any(list(groups[name]) != list(pages) for name, pages in EXPECTED_NAVIGATION.items())):
        raise RuntimeError('Release navigation differs from the independently expected page groups.')


def iter_page_buttons(page):
    # ScrollPage.content is a sibling of the wrapper in the Notebook, not a
    # descendant of its Canvas; start there so hidden tab headers lose nothing.
    content = getattr(page, 'content', page)
    stack = [content]
    while stack:
        widget = stack.pop()
        stack.extend(widget.winfo_children())
        if widget.winfo_class() in ('TButton', 'Button'):
            yield widget


def validate_button_geometry(bounds, container, label):
    x, y, width, height = bounds
    if width <= 1 or height <= 1:
        return False  # Withdrawn windows may not lay out controls at all.
    if x < 0 or y < 0 or x + width > container[0] or y + height > container[1]:
        raise RuntimeError('Button clipped: ' + label)
    return True


def run(output):
    result = {'passed': False, 'frozen': bool(getattr(sys, 'frozen', False)),
              'python': sys.version, 'executable': sys.executable,
              'sys_path': list(sys.path), 'path_environment': os.environ.get('PATH'),
              'pythonhome_environment': os.environ.get('PYTHONHOME'),
              'pythonpath_environment': os.environ.get('PYTHONPATH')}
    root = None
    try:
        from runtime_paths import RESOURCE_ROOT, CACHE_ROOT, LOG_ROOT, SAFETY_LOG_ROOT
        result['resource_root'] = str(RESOURCE_ROOT)
        result['cache_root'] = str(CACHE_ROOT)
        result['log_root'] = str(LOG_ROOT)
        result['safety_log_root'] = str(SAFETY_LOG_ROOT)
        if not result['frozen']:
            raise RuntimeError('Run this check with the built EXE, not the source Python script.')
        bundle = Path(sys._MEIPASS).resolve()
        buffer = ctypes.create_unicode_buffer(32768)
        get_name = ctypes.WinDLL('kernel32', use_last_error=True).GetModuleFileNameW
        get_name.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        get_name.restype = ctypes.c_uint32
        if not get_name(sys.dllhandle, buffer, len(buffer)):
            raise ctypes.WinError(ctypes.get_last_error())
        result['python_dll'] = buffer.value
        if not Path(buffer.value).resolve().is_relative_to(bundle):
            raise RuntimeError('Python DLL was loaded from outside this bundle.')
        if any(not Path(path).resolve().is_relative_to(bundle) for path in sys.path):
            raise RuntimeError('External Python module search path remains enabled.')
        manifest = json.loads((RESOURCE_ROOT / 'bundle_manifest.json').read_text(encoding='utf8'))
        validate_bundle_manifest(manifest)
        modules = sorted(EXPECTED_CORE_MODULES | EXPECTED_ADDITIONAL_MODULES)
        modules += ['frida', 'frida._frida', 'tkinter', 'tkinter.ttk']
        result['modules'] = {}
        for name in modules:
            module = importlib.import_module(name)
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(bundle):
                raise RuntimeError('External module: ' + name)
            result['modules'][name] = str(path)
        result['resources'] = {}
        for resource, expected in manifest['resources'].items():
            path = RESOURCE_ROOT / resource
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError('Missing or changed resource: ' + resource)
            result['resources'][resource] = actual
        # Creating the application while withdrawn exercises every page and Tk
        # resources. No .connect(), .snapshot(), Frida device, or target API call.
        import tkinter as tk
        from app import App
        from release_info import VERSION, read_feature_introduction
        result['version'] = VERSION
        introduction = read_feature_introduction()
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        root.update_idletasks()
        result['game_location_mode'] = 'auto' if app.selected_game_path is None else 'manual'
        if app.selected_game_path is not None or str(app.choose_path_button.cget('state')) != 'normal':
            raise RuntimeError('Portable game path selection is not available at startup.')
        result['manual_game_picker_available'] = True
        result['tabs'] = [app.tabs.tab(tab, 'text') for tab in app.tabs.tabs()]
        validate_release_ui(result['tabs'], VERSION, introduction)
        result['navigation'] = {str(app.navigation.tree.item(group, 'text')):
            [app.navigation._titles[page] for page in app.navigation.tree.get_children(group)]
            for group in app.navigation.tree.get_children()}
        validate_release_navigation(result['navigation'])
        result['feature_introduction_available'] = True
        result['tcl_library'] = str(root.tk.call('info', 'library'))
        result['tk_library'] = str(root.tk.globalgetvar('tk_library'))
        # Python 3.14.7 ships Tcl/Tk 9 with resource ZIPs embedded in its DLLs.
        # Verify their backing files, not the virtual //zipfs: pathname.
        mounts = root.tk.call('zipfs', 'mount') if float(tk.TclVersion) >= 9 else ()
        mounts = root.tk.splitlist(mounts) if isinstance(mounts, str) else mounts
        result['tcl_zip_mounts'] = dict(zip(map(str, mounts[::2]), map(str, mounts[1::2])))
        for library in (result['tcl_library'], result['tk_library']):
            if str(library).startswith('//zipfs:'):
                backing = [value for key, value in result['tcl_zip_mounts'].items()
                           if str(library).startswith(key.rstrip('/') + '/')]
                if not backing or any(not Path(path).resolve().is_relative_to(bundle) for path in backing):
                    raise RuntimeError('Tcl/Tk ZIP resources were loaded from outside this bundle.')
            elif not Path(library).resolve().is_relative_to(bundle):
                raise RuntimeError('Tcl/Tk was loaded from outside this bundle.')
        if app.adapter is not None or app.busy:
            raise RuntimeError('Offline self-test unexpectedly connected to a game.')
        result['minimum_geometry'] = list(root.minsize())
        result['layout_checks'] = []
        result['layout_verified'] = True
        result['layout_mode'] = 'offscreen_mapped'
        # Withdrawn roots can retain 1px container geometry while their children
        # already have requested sizes. Map the offline test window off-screen
        # so layout and stacking are real, without showing a user-facing window.
        root.overrideredirect(True)
        root.geometry('940x800+30000+30000')
        root.deiconify()
        root.update()
        for width, height in ((940, 800), (860, 730)):
            root.geometry(f'{width}x{height}+30000+30000')
            for tab in app.tabs.tabs():
                app.tabs.select(tab)
                root.update()
                page = root.nametowidget(tab)
                page.canvas.yview_moveto(0)
                root.update()
                content, buttons = getattr(page, 'content', page), []
                if not content.winfo_ismapped() or content.winfo_width() <= 1 or content.winfo_height() <= 1:
                    raise RuntimeError('Selected page content is not mapped: ' + str(app.tabs.tab(tab, 'text')))
                if any(root.nametowidget(other).content.winfo_ismapped()
                       for other in app.tabs.tabs() if other != tab):
                    raise RuntimeError('An inactive page remains mapped.')
                controls = [(widget, content, 'scroll_content') for widget in iter_page_buttons(page)]
                controls += [(widget, root, 'window') for widget in (app.connect_button, app.refresh_button,
                    app.about_button, app.choose_path_button, app.auto_path_button)]
                for widget, container, scope in controls:
                    x = widget.winfo_rootx() - container.winfo_rootx()
                    y = widget.winfo_rooty() - container.winfo_rooty()
                    w, h = widget.winfo_width(), widget.winfo_height()
                    # Content may extend vertically below the viewport: its
                    # scrollbar makes those controls reachable. Shared actions
                    # must remain inside the window itself.
                    size = [width, height] if scope == 'window' else [content.winfo_width(), content.winfo_height()]
                    buttons.append({'text': str(widget.cget('text')), 'bounds': [x, y, w, h], 'scope': scope})
                    if not validate_button_geometry([x, y, w, h], size,
                            f'{app.tabs.tab(tab, "text")}/{widget.cget("text")} at {width}x{height}'):
                        raise RuntimeError('Button not laid out in mapped test window: ' + str(widget.cget('text')))
                # Geometry alone misses a sibling Canvas covering the content.
                # Hit-test visible page actions and the shared footer at both
                # scroll extremes; lower actions must be reachable by scrolling.
                for fraction in (0, 1):
                    page.canvas.yview_moveto(fraction)
                    root.update()
                    viewport_top = page.canvas.winfo_rooty()
                    viewport_bottom = viewport_top + page.canvas.winfo_height()
                    visible = [widget for widget in iter_page_buttons(page)
                        if widget.winfo_rooty() >= viewport_top
                        and widget.winfo_rooty()+widget.winfo_height() <= viewport_bottom]
                    for widget in visible + [app.refresh_button, app.connect_button]:
                        hit = root.winfo_containing(widget.winfo_rootx()+widget.winfo_width()//2,
                            widget.winfo_rooty()+widget.winfo_height()//2)
                        if hit != widget:
                            raise RuntimeError('Button covered: ' + str(app.tabs.tab(tab, 'text')) + '/' + str(widget.cget('text')))
                result['layout_checks'].append({'geometry': [width, height],
                    'tab': str(app.tabs.tab(tab, 'text')), 'buttons': buttons})
        for folder in (CACHE_ROOT, LOG_ROOT, SAFETY_LOG_ROOT):
            if folder.resolve().is_relative_to(bundle):
                raise RuntimeError('Persistent state would be lost in the bundle directory.')
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=folder) as handle:
                handle.write(b'WorldApartTrainer offline writeability check')
                handle.flush()
        result['passed'] = True
        result['game_connection_attempted'] = False
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if root is not None:
            root.destroy()
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf8')
    return 0 if result['passed'] else 1
