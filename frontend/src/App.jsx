import React,{useEffect,useMemo,useRef,useState} from 'react';
import {Activity,CalendarDays,Clock,HeartPulse,Mic,MicOff,Phone,PhoneOff,RefreshCw,Stethoscope,Users,Volume2,CheckCircle2,Search,ArrowUpRight} from 'lucide-react';
const API=import.meta.env.VITE_API_URL||'http://localhost:8000'; 
const fmt=(s)=>new Date(s).toLocaleString('en-IN',{dateStyle:'medium',timeStyle:'short'});
export default function App(){
 const [doctors,setDoctors]=useState([]),[slots,setSlots]=useState([]),[appointments,setAppointments]=useState([]),[selected,setSelected]=useState('all'),[search,setSearch]=useState('');
 const [call,setCall]=useState('idle'),[muted,setMuted]=useState(false),[transcript,setTranscript]=useState([{who:'assistant',text:'Hello! I’m VoiceCare. I can help you find, book, or cancel a doctor appointment.'}]);
 const [error,setError]=useState(''),[loading,setLoading]=useState(false),[callId,setCallId]=useState(null),[phone,setPhone]=useState('');
 const [pipecatClient, setPipecatClient] = useState(null);
 const [audioBlocked,setAudioBlocked]=useState(false);
 const es=useRef(null),pc=useRef(null),audioRef=useRef(null),transport=useRef(null);
 async function refresh(){try{const [d,s,a]=await Promise.all([fetch(API+'/api/doctors').then(r=>r.json()),fetch(API+'/api/slots').then(r=>r.json()),fetch(API+'/api/appointments').then(r=>r.json())]);setDoctors(d);setSlots(s);setAppointments(a)}catch(e){setError('API unavailable — start the backend on port 8000.');}}
 useEffect(()=>{refresh();const t=setInterval(refresh,7000);return()=>{clearInterval(t);es.current?.close();pc.current?.close()}},[]);
 const filtered=doctors.filter(d=>(selected==='all'||d.specialty===selected)&&`${d.name} ${d.specialty}`.toLowerCase().includes(search.toLowerCase()));
 const specialties=[...new Set(doctors.map(d=>d.specialty))];
 async function startCall(){
  setError('');setLoading(true);setTranscript([]);
  try{
   const callResponse=await fetch(API+'/api/calls',{method:'POST'});
   const callData=await callResponse.json();
   if(!callResponse.ok)throw Error(callData.detail||'Could not create call session');
   const currentCallId=callData.call_id;
   setCallId(currentCallId);
   es.current?.close();
   es.current=new EventSource(API+'/api/calls/'+encodeURIComponent(currentCallId)+'/events');
   es.current.onmessage=(event)=>{try{const data=JSON.parse(event.data);if(data.who&&data.text)setTranscript(p=>[...p,{who:data.who,text:data.text}])}catch{}};
   const [{PipecatClient},{SmallWebRTCTransport}]=await Promise.all([
    import('@pipecat-ai/client-js'),import('@pipecat-ai/small-webrtc-transport')
   ]);
   const client=new PipecatClient({
    transport:new SmallWebRTCTransport(),
    enableMic:true,enableCam:false,
    callbacks:{
     onConnected:()=>setCall('connected'),
     onDisconnected:()=>{setCall('ended');es.current?.close();if(audioRef.current)audioRef.current.srcObject=null},
     onTrackStarted:(track,participant)=>{if(participant?.local||track.kind!=='audio')return;const player=audioRef.current;if(!player)return;player.srcObject=new MediaStream([track]);player.play().then(()=>setAudioBlocked(false)).catch(()=>setAudioBlocked(true))},
     onTrackStopped:(track,participant)=>{if(participant?.local||track.kind!=='audio')return;if(audioRef.current)audioRef.current.srcObject=null},
     onError:(e)=>setError(e?.message||'Voice connection error')
    }
   });
   setPipecatClient(client);setCall('connecting');
   await client.connect({webrtcUrl:API+'/api/offer?call_id='+encodeURIComponent(currentCallId)});
  }catch(e){es.current?.close();setPipecatClient(null);setError(e?.message||'Could not connect voice agent. Check API keys, backend logs and microphone permission.');setCall('idle')}
  finally{setLoading(false)}
 }
 async function endCall(){es.current?.close();try{await pipecatClient?.disconnect()}catch{}setPipecatClient(null);setCall('ended')}
 async function bookDemo(slot){const p=phone.trim();if(!p){setError('Enter a phone number to book from the dashboard demo.');return}try{const r=await fetch(API+'/api/appointments/book',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({doctor_id:slot.doctor_id,slot_id:slot.slot_id,phone:p})});const j=await r.json();if(!r.ok)throw Error(j.detail);setError('');await refresh()}catch(e){setError(e.message)}}
 const booked=appointments.filter(a=>a.status==='booked').length;
 return <div className="app"><audio ref={audioRef} autoPlay playsInline style={{display:'none'}}/><aside className="sidebar"><div className="brand"><div className="brandmark"><HeartPulse size={21}/></div><div><b>voicecare</b><small>CLINIC OPERATIONS</small></div></div><div className="navlabel">WORKSPACE</div><div className="nav active"><Activity size={17}/> Overview</div><div className="nav"><Stethoscope size={17}/> Doctors</div><div className="nav"><CalendarDays size={17}/> Appointments <span>{booked}</span></div><div className="sidebottom"><div className="secure"><div className="dot"/> SYSTEM OPERATIONAL</div><div className="profile"><div className="avatar">VC</div><div><b>VoiceCare Admin</b><small>Clinic workspace</small></div></div></div></aside>
 <main className="main"><header><div><h1>Good morning <span>—</span></h1><p className="muted">Here’s what’s happening at your clinic today.</p></div><button className="ghost" onClick={refresh}><RefreshCw size={15}/> Refresh data</button></header>
 {error&&<div className="alert">{error}<button onClick={()=>setError('')}>×</button></div>}
 <section className="stats"><div className="stat"><div className="staticon purple"><Users/></div><div><small>DOCTORS</small><strong>{doctors.length.toString().padStart(2,'0')}</strong><span>Available specialists</span></div></div><div className="stat"><div className="staticon blue"><CalendarDays/></div><div><small>OPEN SLOTS</small><strong>{slots.length.toString().padStart(2,'0')}</strong><span>Upcoming availability</span></div></div><div className="stat"><div className="staticon green"><CheckCircle2/></div><div><small>ACTIVE BOOKINGS</small><strong>{booked.toString().padStart(2,'0')}</strong><span>Confirmed appointments</span></div></div><div className="stat"><div className="staticon orange"><Activity/></div><div><small>VOICE AGENT</small><strong className="online">ONLINE</strong><span>Ready to assist callers</span></div></div></section>
 <section className="gridmain"><div className="panel callpanel"><div className="panelhead"><div><div className="eyebrow">VOICE ASSISTANT</div><h2>Talk to your clinic</h2><p className="muted">Book or manage appointments with a natural conversation.</p></div><span className={'status '+call}>{call==='connected'?'LIVE':call==='connecting'?'CONNECTING':call==='ended'?'ENDED':'READY'}</span></div>
 <div className="callstage"><div className={'orb '+call}><div className="orbinner"><HeartPulse size={34}/></div></div><div className="calltitle">{call==='connected'?'You’re connected':call==='connecting'?'Connecting securely…':call==='ended'?'Call ended':'VoiceCare is ready'}</div><div className="callsub">{call==='connected'?'Speak naturally. I’m listening.': 'Your AI-powered appointment assistant is standing by.'}</div><div className="callactions">{call==='connected'?<><button className={'round '+(muted?'selected':'')} onClick={()=>setMuted(!muted)}><MicOff/></button><button className="endcall" onClick={endCall}><PhoneOff size={18}/> End call</button></>:<button className="startcall" disabled={loading||call==='connecting'} onClick={startCall}>{loading?<RefreshCw className="spin"/>:<Phone size={17}/>} {loading?'Starting…':'Try a call'}</button>}{audioBlocked&&<button className="startcall" onClick={()=>audioRef.current?.play().then(()=>setAudioBlocked(false)).catch(()=>setError('Browser blocked assistant audio. Check your sound output and try again.'))}>Enable assistant audio</button>}</div></div>
 <div className="transcript"><div className="transhead"><b>Live transcript</b><span><i/> {call==='connected'?'Listening':'Conversation preview'}</span></div><div className="messages">{transcript.map((m,i)=><div className={'message '+m.who} key={i}><div className="bubblelabel">{m.who==='you'?'YOU':'VOICECARE'}</div><p>{m.text}</p></div>)}</div></div></div>
 <div className="panel doctorspanel"><div className="panelhead"><div><div className="eyebrow">CARE TEAM</div><h2>Our doctors</h2><p className="muted">Browse specialists and their next openings.</p></div><span className="count">{doctors.length} total</span></div><div className="search"><Search size={15}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search doctors…"/></div><div className="filters"><button className={selected==='all'?'chosen':''} onClick={()=>setSelected('all')}>All</button>{specialties.map(s=><button className={selected===s?'chosen':''} onClick={()=>setSelected(s)} key={s}>{s}</button>)}</div><div className="doctorlist">{filtered.map((d,i)=><div className="doctor" key={d.id}><div className={'docavatar a'+i}>{d.name.split(' ').slice(1).map(x=>x[0]).join('').replace('.','')}</div><div className="docinfo"><b>{d.name}</b><span>{d.specialty} · {d.experience}</span><small><i/> {slots.filter(s=>s.doctor_id===d.id).length} upcoming slots</small></div><button className="iconbtn" title="View availability" onClick={()=>{setSelected(d.specialty);document.getElementById('availability')?.scrollIntoView({behavior:'smooth'})}}><ArrowUpRight size={17}/></button></div>)}</div></div></section>
 <section className="panel lower" id="availability"><div className="panelhead"><div><div className="eyebrow">SCHEDULING</div><h2>Upcoming availability</h2><p className="muted">Demo booking can be made directly from a slot.</p></div><input className="phoneinput" value={phone} onChange={e=>setPhone(e.target.value)} placeholder="Patient phone number"/></div><div className="tablewrap"><table><thead><tr><th>DOCTOR</th><th>SPECIALTY</th><th>DATE & TIME</th><th>STATUS</th><th/></tr></thead><tbody>{slots.slice(0,8).map(s=><tr key={s.slot_id}><td><b>{s.doctor_name}</b></td><td>{s.specialty}</td><td>{fmt(s.starts_at)}</td><td><span className="available">Available</span></td><td><button className="bookbtn" onClick={()=>bookDemo(s)}>Book slot</button></td></tr>)}</tbody></table>{!slots.length&&<div className="empty">No upcoming slots found.</div>}</div></section>
 <section className="panel lower"><div className="panelhead"><div><div className="eyebrow">PATIENT SCHEDULE</div><h2>Recent appointments</h2><p className="muted">Bookings and cancellations update automatically.</p></div><span className="count">{appointments.length} records</span></div><div className="tablewrap"><table><thead><tr><th>REFERENCE</th><th>DOCTOR</th><th>PHONE</th><th>DATE & TIME</th><th>STATUS</th><th>ACTION</th></tr></thead><tbody>{appointments.slice(0,8).map(a=><tr key={a.id}><td>VC-{String(a.id).padStart(4,'0')}</td><td><b>{a.doctor_name}</b></td><td>{a.phone}</td><td>{fmt(a.starts_at)}</td><td><span className={a.status==='booked'?'available':'cancelled'}>{a.status}</span></td><td>{a.status==='booked'?<button className="bookbtn" onClick={async()=>{if(!window.confirm('Cancel this appointment?'))return;const r=await fetch(API+'/api/appointments/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({phone:a.phone,appointment_id:a.id})});const j=await r.json();if(!r.ok)setError(j.detail||'Cancellation failed');else await refresh()}}>Cancel</button>:'—'}</td></tr>)}</tbody></table>{!appointments.length&&<div className="empty">No appointments yet. Start a call or book a demo slot.</div>}</div></section>
 <footer>VOICECARE <span>·</span> INTERNAL CLINIC WORKSPACE <span className="footright">Built for reliable patient scheduling</span></footer></main></div>
}
