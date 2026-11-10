"use client";
import { useState } from "react";
import { Button } from "./ui/button";
import { api,json,Field,type Task } from "./shared";
export type Model={role:string;provider?:string;base_url?:string;model?:string;key_configured:boolean};
export function visibleModels(configs: Model[]): Model[] {
 return ["diff", "classifier"].flatMap(role => {
  const config = configs.find(item => item.role === role);
  return config ? [config] : [];
 });
}
export function ModelForm({config,busy,task}:{config:Model;busy:boolean;task:Task}){
 const [provider,setProvider]=useState(config.provider||"openai"),[base,setBase]=useState(config.base_url||"https://api.openai.com/v1"),[model,setModel]=useState(config.model||""),[key,setKey]=useState(""),[saved,setSaved]=useState(config.key_configured),[message,setMessage]=useState("");
 if (config.role !== "diff" && config.role !== "classifier") return null;
 return <form className="card" onSubmit={e=>{e.preventDefault();void task(async()=>{await api("/admin/models/"+config.role,json("PUT",{provider,base_url:base,model,api_key:key||null}));setKey("");setSaved(true);setMessage("Configuration saved.")})}}>
 <div className="row spread"><h2>{config.role==="diff"?"Git Diff Summarizer":"Central Classifier"}</h2><span className="pill">{saved?"Key configured ••••••••":"Not configured"}</span></div>
 {config.role==="classifier"&&<p>Predicts flakiness from saved B2_o1 evidence and returns a probability between 0 and 1.</p>}
 <div className="fields"><Field label="Provider protocol"><select value={provider} onChange={e=>{setProvider(e.target.value);setBase(e.target.value==="anthropic"?"https://api.anthropic.com/v1":"https://api.openai.com/v1")}}><option value="openai">OpenAI-compatible endpoint</option><option value="anthropic">Anthropic Messages API</option></select></Field>
 <Field label="API base URL"><input type="url" required value={base} onChange={e=>setBase(e.target.value)}/></Field><Field label="Model name"><input required value={model} onChange={e=>setModel(e.target.value)}/></Field><Field label={saved?"Replace API key (blank keeps saved key)":"API key"}><input type="password" autoComplete="new-password" required={!saved} value={key} onChange={e=>setKey(e.target.value)} placeholder={saved?"••••••••":"Enter key securely"}/></Field></div>
 <div className="row"><Button type="submit" disabled={busy}>Save configuration</Button><Button type="button" variant="outline" disabled={busy||!saved} onClick={()=>task(async()=>{await api("/admin/models/"+config.role+"/test",{method:"POST"});setMessage("Saved connection tested successfully.")})}>Test saved connection</Button><span className="hint" role="status">{message}</span></div></form>;
}
