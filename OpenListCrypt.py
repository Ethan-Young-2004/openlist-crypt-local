import os
import tkinter as tk
import json
import threading
import queue
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
from rclone import Crypt

def process_file_job(job):
    source,target,decrypt,password,salt,obscured,encoding=job
    if obscured:
        c=Crypt(password,salt,passwd_obscured=True,name_encoding=encoding)
    else:
        salt_value=salt if salt else bytes.fromhex("a80df43a8fbd0308a7cab83e581f86b1")
        c=Crypt(password,salt_value,name_encoding=encoding)
    (c.File.file_decrypt if decrypt else c.File.file_encrypt)(source,target)
    return source,target

class App:
    def __init__(self, root):
        self.root=root
        root.title("OpenList Crypt 本地加密工具")
        root.geometry("760x680")
        self.src=tk.StringVar(); self.dst=tk.StringVar()
        self.password=tk.StringVar(); self.salt=tk.StringVar()
        self.mode=tk.StringVar(value="加密")
        self.fname=tk.StringVar(value="standard")
        self.encoding=tk.StringVar(value="base64")
        self.suffix=tk.StringVar(value=".bin")
        self.direnc=tk.BooleanVar(value=True)
        self.obscured=tk.BooleanVar(value=False)
        self.savepass=tk.BooleanVar(value=False)
        self.worker_count=tk.IntVar(value=max(1,min(os.cpu_count() or 4,16)))
        self.config_path=Path(os.environ.get("LOCALAPPDATA",Path.home()))/"OpenListCrypt"/"settings.json"
        f=ttk.Frame(root,padding=16); f.pack(fill="both",expand=True)
        f.columnconfigure(1,weight=1); f.rowconfigure(10,weight=1)
        ttk.Label(f,text="输入路径（可拖拽文件或文件夹到此窗口）").grid(row=0,column=0,columnspan=3,sticky="w")
        ttk.Button(f,text="选择文件夹",command=self.pick_folder).grid(row=1,column=0,sticky="w",pady=5)
        ttk.Button(f,text="选择文件",command=self.pick_file).grid(row=1,column=1,sticky="w",pady=5)
        ttk.Label(f,textvariable=self.src,wraplength=520).grid(row=2,column=0,columnspan=3,sticky="w")
        root.drop_target_register(DND_FILES); root.dnd_bind("<<Drop>>",self.drop)
        self.row(f,"输出目录",self.dst,3,lambda:self.pick_output())
        self.row(f,"密码",self.password,4,show="•")
        self.row(f,"盐",self.salt,5,show="•")
        ttk.Checkbutton(f,text="保存密码和盐到本机",variable=self.savepass,command=self.save_settings).grid(row=6,column=1,sticky="w")
        ttk.Checkbutton(f,text="输入的是 OpenList 的 ___Obfuscated___ 混淆值",variable=self.obscured).grid(row=7,column=1,sticky="w")
        ttk.Label(f,text="操作").grid(row=8,column=0,sticky="w")
        ttk.Combobox(f,textvariable=self.mode,values=["加密","解密"],state="readonly",width=14).grid(row=8,column=1,sticky="w")
        opts=ttk.Frame(f); opts.grid(row=9,column=0,columnspan=3,sticky="ew",pady=8)
        ttk.Label(opts,text="文件名加密").pack(side="left")
        ttk.Combobox(opts,textvariable=self.fname,values=["standard","off","obfuscate"],state="readonly",width=12).pack(side="left",padx=5)
        ttk.Label(opts,text="编码").pack(side="left")
        ttk.Combobox(opts,textvariable=self.encoding,values=["base64","base32","base32768"],state="readonly",width=12).pack(side="left",padx=5)
        ttk.Label(opts,text="后缀").pack(side="left")
        ttk.Entry(opts,textvariable=self.suffix,width=8).pack(side="left",padx=5)
        ttk.Checkbutton(opts,text="加密目录名",variable=self.direnc).pack(side="left",padx=5)
        ttk.Label(opts,text="并行进程").pack(side="left",padx=(8,2))
        ttk.Spinbox(opts,from_=1,to=32,textvariable=self.worker_count,width=4).pack(side="left")
        self.log=tk.Text(f,height=12,wrap="word"); self.log.grid(row=10,column=0,columnspan=3,sticky="nsew")
        self.start_button=ttk.Button(f,text="按当前选项开始处理",command=self.run)
        self.start_button.grid(row=11,column=2,sticky="e",pady=10)
        self.load_settings()
    def row(self,parent,label,var,i,button=None,show=None):
        ttk.Label(parent,text=label).grid(row=i,column=0,sticky="w",pady=5)
        ttk.Entry(parent,textvariable=var,show=show).grid(row=i,column=1,sticky="ew",padx=8)
        if button: ttk.Button(parent,text="浏览…",command=button).grid(row=i,column=2)
    def pick_folder(self):
        p=filedialog.askdirectory()
        if p:self.src.set(p)
    def pick_file(self):
        p=filedialog.askopenfilename()
        if p:self.src.set(p)
    def pick_output(self):
        p=filedialog.askdirectory()
        if p:self.dst.set(p)
    def drop(self,event):
        paths=self.root.tk.splitlist(event.data)
        if paths:self.src.set(paths[0]); self.run()
    def load_settings(self):
        try:
            d=json.loads(self.config_path.read_text(encoding="utf-8"))
            self.password.set(d.get("password","")); self.salt.set(d.get("salt",""))
            self.savepass.set(bool(d.get("saved",False)))
        except Exception: pass
    def save_settings(self):
        try:
            self.config_path.parent.mkdir(parents=True,exist_ok=True)
            d={"saved":self.savepass.get()}
            if self.savepass.get(): d.update(password=self.password.get(),salt=self.salt.get())
            self.config_path.write_text(json.dumps(d,ensure_ascii=False),encoding="utf-8")
        except Exception as e: messagebox.showerror("保存失败",str(e))
    def run(self):
        if getattr(self,"busy",False): return
        self.busy=True; self.start_button.configure(state="disabled")
        self.events=queue.Queue()
        threading.Thread(target=self._run_task,daemon=True).start()
        self.root.after(100,self.poll_events)
    def poll_events(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=="log": self.log.insert("end",value+"\n"); self.log.see("end")
                elif kind=="clear": self.log.delete("1.0","end")
                elif kind=="done":
                    self.busy=False; self.start_button.configure(state="normal")
                    messagebox.showinfo("完成","处理完成")
                elif kind=="error":
                    self.busy=False; self.start_button.configure(state="normal")
                    messagebox.showerror("处理失败",value)
        except queue.Empty: pass
        if self.busy: self.root.after(100,self.poll_events)
    def _run_task(self):
        try:
            src=Path(self.src.get()); dst=Path(self.dst.get())
            if not src.exists(): raise ValueError("请先选择或拖入文件/文件夹")
            if not dst: raise ValueError("请选择输出目录")
            pwd=self.password.get(); salt=self.salt.get()
            if not pwd: raise ValueError("请填写密码")
            if self.savepass.get(): self.save_settings()
            if self.obscured.get():
                pwd=pwd.removeprefix("___Obfuscated___")
                salt=salt.removeprefix("___Obfuscated___")
                if not salt: raise ValueError("混淆值模式需要同时填写密码和盐")
            if self.obscured.get():
                c=Crypt(pwd,salt,passwd_obscured=True,name_encoding=self.encoding.get())
            else:
                salt_value=salt if salt else bytes.fromhex("a80df43a8fbd0308a7cab83e581f86b1")
                c=Crypt(pwd,salt_value,name_encoding=self.encoding.get())
            dst.mkdir(parents=True,exist_ok=True); self.events.put(("clear",None))
            is_tree=src.is_dir()
            items=[src] if src.is_file() else [src]+sorted(src.rglob("*"))
            decrypt=self.mode.get()=="解密"
            out_root=dst
            if is_tree:
                root_name=src.name
                if self.direnc.get():
                    if decrypt:
                        try:
                            root_name=c.Name.standard_decrypt(root_name)
                        except Exception as e:
                            raise ValueError(f"无法解密源文件夹名称“{root_name}”。请确认已勾选“加密目录名”，并核对密码和盐。") from e
                    else:
                        root_name=c.Name.standard_encrypt(root_name)
                out_root=dst/root_name
            jobs=[]
            for item in items:
                rel=item.name if src.is_file() else ("" if item==src else str(item.relative_to(src)))
                parts=Path(rel).parts; transformed=[]
                for j,part in enumerate(parts):
                    isfile=item.is_file() and j==len(parts)-1
                    use=(self.fname.get()!="off") if isfile else self.direnc.get()
                    if use:
                        if isfile and self.fname.get()=="obfuscate":
                            enc,dec=c.Name.obfuscate_encrypt,c.Name.obfuscate_decrypt
                        else: enc,dec=c.Name.standard_encrypt,c.Name.standard_decrypt
                        part=(dec if decrypt else enc)(part)
                    elif isfile:
                        part=part.removesuffix(self.suffix.get()) if decrypt else part+self.suffix.get()
                    transformed.append(part)
                out=(out_root.joinpath(*transformed) if is_tree else dst.joinpath(*transformed))
                if item.is_dir(): out.mkdir(parents=True,exist_ok=True); continue
                out.parent.mkdir(parents=True,exist_ok=True)
                jobs.append((item,out))
            # Small and medium files benefit from file-level parallelism. Each worker
            # uses at most two crypto workers, keeping total concurrency bounded.
            work=[(str(item),str(out),decrypt,pwd,salt,self.obscured.get(),self.encoding.get()) for item,out in jobs]
            if work:
                with ProcessPoolExecutor(max_workers=min(self.worker_count.get(),len(work),32)) as pool:
                    for source,target in pool.map(process_file_job,work,chunksize=1):
                        self.events.put(("log",f"{Path(source).name} → {target}"))
            self.events.put(("done",None))
        except Exception as e: self.events.put(("error",str(e)))

if __name__=="__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    root=TkinterDnD.Tk(); App(root); root.mainloop()
