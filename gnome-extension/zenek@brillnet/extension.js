import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// Stable entry point; each locally installed build imports its own ESM path.
export default class ZenekLoader extends Extension {
    enable() {
        const generation=(this._generation??0)+1;this._generation=generation;
        this.dir.get_child('build.json').load_contents_async(null,async (f,result)=>{
            try {
                const [,bytes]=f.load_contents_finish(result);
                const manifest=JSON.parse(new TextDecoder().decode(bytes));
                if(!/^companion-[a-f0-9]{16}\.js$/.test(manifest.module))throw new Error('Invalid Zenek module');
                const module=await import(this.dir.get_child(manifest.module).get_uri());
                if(this._generation!==generation)return;
                this._companion=new module.default({...this.metadata,dir:this.dir,path:this.path});
                this._companion.enable();
            } catch(error) {
                this._companion?.disable();this._companion=null;
                console.error(`Zenek failed to load: ${error.message}`);
            }
        });
    }
    disable(){this._generation=(this._generation??0)+1;this._companion?.disable();this._companion=null;}
}
