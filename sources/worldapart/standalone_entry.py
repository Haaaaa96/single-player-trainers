"""Standalone entry point; no shell invocation or external Python interpreter."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog='WorldApartTrainer')
    parser.add_argument('--self-test', type=Path, metavar='JSON', help='Offline packaging smoke test; never connects to the game')
    parser.add_argument('--update-check', type=Path, metavar='JSON', help='Read-only check of all pages in an already running game; no native calls or modifications')
    parser.add_argument('--native-host', type=Path, metavar='CONFIG', help=argparse.SUPPRESS)
    parser.add_argument('--lifetime-self-test', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--lifetime-self-test-child', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    modes = (args.self_test, args.update_check, args.native_host,
             args.lifetime_self_test, args.lifetime_self_test_child)
    if sum(mode is not None for mode in modes) > 1:
        parser.error('Choose exactly one operation mode.')
    if args.update_check is not None:
        from audit_update_readonly import main as update_check
        return update_check(['--output', str(args.update_check)])
    if args.lifetime_self_test is not None or args.lifetime_self_test_child is not None:
        from standalone_lifetime_selftest import launch, child
        return launch(args.lifetime_self_test) if args.lifetime_self_test is not None else child(args.lifetime_self_test_child)
    if args.native_host is not None:
        from native_broker_host import main
        return main(args.native_host)
    if args.self_test is not None:
        try:
            from standalone_selftest import run
            return run(args.self_test)
        except Exception:
            import json
            import traceback
            args.self_test.parent.mkdir(parents=True, exist_ok=True)
            args.self_test.write_text(json.dumps({'passed': False, 'error': traceback.format_exc()}), encoding='utf8')
            return 1
    from runtime_paths import initialize_runtime
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        initialize_runtime()
        from app import App
        App(root)
    except Exception as error:
        messagebox.showerror('WorldApartTrainer', f'启动失败：{error}', parent=root)
        root.destroy()
        return 1
    root.deiconify()
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
