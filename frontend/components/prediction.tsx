"use client";
import { Activity, Loader2 } from "lucide-react";
import { Button } from "./ui/button";
import { api, Code, type Test, type Task } from "./shared";

export function PredictionPanel({analysisId,test,busy,task,reload}:{analysisId:string;test:Test;busy:boolean;task:Task;reload:()=>Promise<void>}){
 const prediction=test.prediction||{status:"not_started"};
 if(!test.payload)return <div className="notice">This test needs a complete B2_o1 evidence payload before prediction can run.</div>;
 if(prediction.status==="running")return <div className="notice row" role="status"><Loader2 className="spinner" size={18}/>Predicting flakiness from the saved evidence…</div>;
 if(prediction.status==="failed")return <div className="notice error" role="alert">{prediction.message||"Analysis could not be completed. Please contact the administrator."}
 {prediction.technical_error&&<details><summary>Administrator error details</summary><Code value={prediction.technical_error}/></details>}
 <p className="hint">This attempt is saved. No automatic retry was made.</p></div>;
 if(prediction.status==="complete"&&typeof prediction.flaky_probability==="number"){
  const percent=prediction.flaky_probability*100;
  const color=percent < 100/3 ? "#15803d" : percent < 200/3 ? "#a16207" : "#b91c1c";
  return <div><div className="caption">Estimated flakiness</div><div style={{fontSize:56,fontWeight:700,letterSpacing:"-2px",color}}>{percent.toFixed(1)}<span style={{fontSize:26}}>%</span></div>
   <div role="progressbar" aria-label="Estimated flakiness probability" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} style={{width:"100%",height:12,background:"var(--line)",borderRadius:6,overflow:"hidden"}}><div style={{width:Math.max(0,Math.min(100,percent))+"%",height:"100%",background:color,borderRadius:6}}/></div>
   <div className="row spread hint" style={{marginTop:8}}><span>0% · Low flakiness</span><span>50%</span><span>100% · High flakiness</span></div>
   <p>This is an LLM estimate, not a calibrated statistical probability.</p>
   <h3>Why this estimate?</h3>
   {prediction.reasons?.length?<ul style={{listStyleType:"disc",paddingLeft:22,lineHeight:1.7,marginBottom:20}}>{prediction.reasons.map((reason,index)=><li key={index} style={{marginBottom:8}}>{reason}</li>)}</ul>:<p className="hint">This result was saved before explanatory reasons were added.</p>}
   <details><summary>Model response JSON</summary><Code value={{flaky_probability:prediction.flaky_probability,...(prediction.reasons?.length?{reasons:prediction.reasons}:{})}}/></details>
   <details><summary>Prediction provenance</summary><Code value={{model:prediction.model_reference,prompt_sha256:prediction.prompt_sha256,payload:test.payload_reference}}/></details></div>;
 }
 return <div><h3>Predict this test’s flakiness</h3><p>The central model receives the saved B2_o1 JSON using the research prompt and its two fixed examples, with updated output instructions for concise reasons. The result is a probability between 0 and 1 plus evidence-based bullet points.</p>
 <Button disabled={busy} onClick={()=>task(async()=>{await api("/analyses/"+analysisId+"/tests/"+test.id+"/predict",{method:"POST"});await reload()})}><Activity size={16}/>Predict flakiness</Button>
 <p className="hint" style={{marginTop:14}}>Uses the administrator’s saved central-model connection. Evidence extraction will not run again.</p></div>;
}
