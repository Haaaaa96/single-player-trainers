"""Smithing completion and saved talent balance, with independent stale targets."""
import tkinter as tk
from tkinter import ttk, messagebox

from acquisition_adapter import native_calls_pending
from crafting_talents import parse_crafting_talent_value, validate_crafting_talent_value
from write_guard import Refused, UncertainWrite


class CraftingPanel:
    def __init__(self, app):
        self.app, self.adapter = app, None
        self.state, self.talent_state = None, None
        frame = ttk.Frame(app.tabs, padding=14)
        app.tabs.add(frame, text='炼器辅助')
        heading = ttk.Frame(frame)
        heading.pack(fill='x')
        ttk.Label(heading, text='炼器辅助', font=('Microsoft YaHei UI',14,'bold')).pack(side='left')
        self.detect_button = ttk.Button(heading,text='读取 / 刷新',command=self.detect)
        self.detect_button.pack(side='right')
        box = ttk.LabelFrame(frame,text='完成当前炼器',padding=12)
        box.pack(fill='x',pady=(14,8))
        self.round_note = tk.StringVar(value='进入游戏的炼器棋盘后读取。')
        ttk.Label(box,textvariable=self.round_note,wraplength=530).pack(fill='x')
        self.complete_button = ttk.Button(box,text='最高品阶并激活全部词条',command=self.complete)
        self.complete_button.pack(anchor='w',pady=10)
        ttk.Label(box,text='按当前器胚的最高配置品阶与全部词条能量门槛完成。已有有效词条保留，'
                  '新词条仍由游戏随机生成，不保证随机数值最高。材料消耗和成品由游戏原流程结算。',
                  wraplength=530).pack(fill='x')
        talent = ttk.LabelFrame(frame,text='炼器天赋点',padding=12)
        talent.pack(fill='x',pady=8)
        self.current,self.input = tk.StringVar(value='—'),tk.StringVar()
        self.talent_note = tk.StringVar(value='请先关闭游戏内天赋页，再读取。')
        ttk.Label(talent,text='当前点数').grid(row=0,column=0,sticky='w')
        ttk.Label(talent,textvariable=self.current,font=('Segoe UI',18,'bold')).grid(row=0,column=1,sticky='w',padx=12)
        ttk.Label(talent,text='目标点数').grid(row=1,column=0,sticky='w',pady=8)
        self.entry = ttk.Entry(talent,textvariable=self.input,width=14)
        self.entry.grid(row=1,column=1,padx=12,sticky='w')
        self.set_button = ttk.Button(talent,text='设置',command=self.set_talents)
        self.set_button.grid(row=1,column=2,sticky='w')
        ttk.Label(talent,textvariable=self.talent_note,wraplength=530).grid(row=2,column=0,columnspan=3,sticky='w',pady=(4,0))
        ttk.Label(frame,text='天赋点目标为0～1000的整数。先关闭游戏内炼器天赋页和棋盘，设置后重新打开天赋页。'
                  '\n自动完成后请在游戏的结果页继续并核对成品；游戏可能自动保存。',wraplength=560).pack(fill='x',pady=10)
        self.update_enabled(False)

    def available(self):
        return (not self.app.busy and self.app.adapter is not None
                and getattr(self.app.adapter,'write_enabled',True) is not False
                and getattr(self.app.adapter,'blocked',False) is not True
                and (self.adapter is None or (getattr(self.adapter,'blocked',False) is not True
                     and getattr(getattr(self.adapter,'talents',None),'blocked',False) is not True))
                and not native_calls_pending())

    def update_enabled(self, enabled):
        ready = bool(enabled and self.available())
        self.detect_button.configure(state='normal' if ready else 'disabled')
        self.complete_button.configure(state='normal' if ready and self.state and self.state.get('can_complete') else 'disabled')
        target=(self.talent_state or {}).get('target')
        editable=ready and target and target.can_edit and self.talent_state.get('can_edit')
        for widget in (self.entry,self.set_button):
            widget.configure(state='normal' if editable else 'disabled')

    def clear(self):
        self.state,self.talent_state=None,None
        self.current.set('—');self.input.set('')

    def disconnect(self):
        if self.adapter is not None:
            self.adapter.close()
        self.adapter=None
        self.clear()
        self.round_note.set('先连接游戏，再读取炼器状态。')
        self.talent_note.set('请先读取。')
        self.update_enabled(False)

    def detect(self):
        if not self.available():
            return
        self.clear()
        self.update_enabled(False)
        game=self.app.adapter
        def job():
            from crafting_adapter import CraftingAdapter
            if self.adapter is None:
                self.adapter=CraftingAdapter(game)
            result={}
            for name,read in (('round',self.adapter.snapshot),('talents',self.adapter.talents.snapshot)):
                try:
                    result[name]=read()
                except UncertainWrite:
                    raise
                except Refused as error:
                    result[name]=dict(reason=str(error))
            return result
        self.app.work(job,self.render,readonly=True)

    def render(self, result):
        self.clear()
        self.state=result.get('round')
        self.talent_state=result.get('talents')
        state=self.state or {}
        self.round_note.set(state.get('reason') or (
            f"当前分数 {state.get('score',0)}；配置最高品阶 {state.get('highest_tier','—')}；"
            f"已激活词条 {state.get('activated_count',0)}/{state.get('effect_count',0)}。"))
        talent=self.talent_state or {}
        target=talent.get('target')
        if target is not None:
            self.current.set(str(target.value))
            if target.can_edit and talent.get('can_edit'):
                self.input.set(str(target.value))
        self.talent_note.set(talent.get('reason') or '可设置目标点数；设置后重开游戏内天赋页。')
        self.update_enabled(True)

    def complete(self):
        if not self.available() or self.adapter is None or not self.state or not self.state.get('can_complete'):
            return
        shown,adapter=self.state,self.adapter
        self.clear()
        self.update_enabled(False)
        def job():
            try:
                return adapter.solve(shown)
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_called=str(error))
        def success(result):
            self.round_note.set(result.get('not_called') or result['message'])
            self.talent_note.set('当前目标已清空，请重新读取。')
            self.app.status.set('未完成炼器；请重新读取。' if 'not_called' in result else '炼器已开始原生结算，请回游戏继续。')
            self.update_enabled(True)
        self.app.work(job,success)

    def set_talents(self):
        if not self.available() or self.adapter is None or not self.talent_state or not self.talent_state.get('can_edit'):
            return
        shown=self.talent_state.get('target')
        if shown is None or not shown.can_edit:
            return
        try:
            value=parse_crafting_talent_value(self.input.get())
            validate_crafting_talent_value(shown,value)
        except Refused as error:
            messagebox.showwarning('检查目标点数',str(error),parent=self.app.root)
            return
        adapter=self.adapter
        self.clear()
        self.update_enabled(False)
        def job():
            try:
                return dict(target=adapter.talents.set_value(shown,value))
            except UncertainWrite:
                raise
            except Refused as error:
                return dict(not_written=str(error))
        def success(result):
            if 'not_written' in result:
                self.talent_note.set(result['not_written']+' 请重新读取。')
                self.app.status.set('炼器天赋点未修改。')
            else:
                self.current.set(str(result['target'].value))
                self.talent_note.set('点数已复读确认，请重开游戏内天赋页查看；下一次操作前重新读取。')
                self.app.status.set(f'炼器天赋点：{shown.value} → {value}。')
            self.round_note.set('请重新读取炼器状态。')
            self.update_enabled(True)
        self.app.work(job,success)
