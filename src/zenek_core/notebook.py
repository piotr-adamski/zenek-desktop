"""Text notes under this source checkout; no access to code or other paths."""
from contextlib import contextmanager
import os
from pathlib import Path,PurePosixPath
import stat
import uuid

from .privacy import safe_text

ROOT=Path(__file__).resolve().parents[2]/'notebook'
EXTENSIONS={'.md','.txt','.json','.jsonl','.csv','.tsv'}


class Notebook:
    def __init__(self,root=ROOT):self.root=Path(root)

    @contextmanager
    def parent(self,path,create=False):
        parts=PurePosixPath(path).parts if isinstance(path,str) else ()
        if not parts or path.startswith('/') or '\\' in path or any(p in ('.','..') or p.startswith('.') for p in parts) or Path(parts[-1]).suffix.lower() not in EXTENSIONS:
            raise ValueError('Podaj względną ścieżkę notatki tekstowej we własnym notebook/')
        # Every component is opened relative to a verified directory descriptor.
        # Symlinks cannot turn a note operation into access outside the notebook.
        if create:
            try:os.mkdir(self.root,0o700)
            except FileExistsError:pass
        descriptors=[]
        try:
            descriptor=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);descriptors.append(descriptor)
            for part in parts[:-1]:
                if create:
                    try:os.mkdir(part,0o700,dir_fd=descriptor)
                    except FileExistsError:pass
                descriptor=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor);descriptors.append(descriptor)
            yield descriptor,parts[-1]
        except OSError as error:raise ValueError('Notatka niedostępna lub ścieżka prowadzi przez dowiązanie') from error
        finally:
            for descriptor in reversed(descriptors):os.close(descriptor)

    def list(self):
        if not self.root.exists():return []
        if self.root.is_symlink():raise ValueError('Notatnik nie może być dowiązaniem')
        entries=[]
        for directory,subdirs,files in os.walk(self.root,followlinks=False):
            subdirs[:]=[name for name in subdirs if not name.startswith('.') and not (Path(directory)/name).is_symlink()]
            for name in files:
                path=Path(directory)/name;info=path.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_nlink==1 and path.suffix.lower() in EXTENSIONS and not name.startswith('.'):
                    entries.append(dict(path=path.relative_to(self.root).as_posix(),bytes=info.st_size,updated=info.st_mtime))
        return sorted(entries,key=lambda row:row['updated'],reverse=True)

    def read(self,path):
        with self.parent(path) as (directory,name):
            descriptor=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=directory)
            with os.fdopen(descriptor,'r',encoding='utf-8') as source:
                info=os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('To nie jest własna notatka')
                return safe_text(source.read(100001),100000)

    def write(self,path,text):
        safe_text(text,100000)
        with self.parent(path,create=True) as (directory,name):
            try:
                info=os.stat(name,dir_fd=directory,follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('To nie jest własna notatka')
            except FileNotFoundError:pass
            temporary='.note-'+uuid.uuid4().hex
            descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            try:
                with os.fdopen(descriptor,'w',encoding='utf-8') as output:
                    output.write(text);output.flush();os.fsync(output.fileno())
                os.replace(temporary,name,src_dir_fd=directory,dst_dir_fd=directory)
            finally:
                try:os.unlink(temporary,dir_fd=directory)
                except FileNotFoundError:pass
        return dict(path=path,bytes=len(text.encode('utf-8')),status='written')
