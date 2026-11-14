let csrfToken='';
export function setAuthCsrfToken(value:string){csrfToken=value;}
export class ApiError extends Error{constructor(message:string,public status:number){super(message);}}
export async function api<T>(path:string,body?:unknown):Promise<T>{
  const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?undefined:{'Content-Type':'application/json','X-CSRF-Token':csrfToken},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  const data=await response.json();if(!response.ok)throw new ApiError(data.error||`Request failed (${response.status})`,response.status);return data as T;
}
export const money=(value:number|undefined|null)=>typeof value==='number'&&Number.isFinite(value)?new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:2}).format(value):'—';
export const signed=(value:number)=>`${value>=0?'+':''}${value.toFixed(2)}%`;
export const stamp=(value:string|undefined)=>value?new Date(value).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}):'—';
