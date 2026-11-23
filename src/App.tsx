import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowDownRight, ArrowUpRight, Bell, Bookmark, Boxes, ChartNoAxesCombined, ChevronDown, CircleHelp, Database, Download, ExternalLink, Filter, Gauge, LayoutDashboard, Menu, MoreHorizontal, PackageSearch, Search, Settings, ShieldCheck, SlidersHorizontal, Sparkles, TrendingUp, Upload, X, Zap } from 'lucide-react'
import { locations, money, products as demoProducts } from './data'
import { API_BASE_URL, API_READ_TOKEN, getAnalysisStatus, getApiHealth, getExportListings, getMarketOverview, getMarketplaceSources, getRecentListings } from './api'
import type { ApiListing, MarketOverview, MarketplaceSource } from './api'
import { buildAnalysisPayload, buildLocalAnalysis, median, parseListingsCsv, toCsv } from './intelligence'
import { isArrayOf, isBoolean, isNumberArray, readStored, writeStored } from './storage'
import type { MarketAnalysisPayload, Page, Product, WorkspaceSettings } from './types'
import { Metric } from './components/Metric'
import { AnalysisResult } from './components/AnalysisResult'
import { ProductCard } from './components/ProductCard'
import { ProductModal } from './components/ProductModal'
import { ProductTable } from './components/ProductTable'

const nav: {label:Page; icon:typeof Activity; group:string}[] = [
 {label:'Overview',icon:LayoutDashboard,group:'WORKSPACE'},
 {label:'Products',icon:PackageSearch,group:'WORKSPACE'},
 {label:'Trending',icon:TrendingUp,group:'INSIGHTS'},
 {label:'Price intelligence',icon:ChartNoAxesCombined,group:'INSIGHTS'},
 {label:'Opportunities',icon:Zap,group:'INSIGHTS'},
 {label:'Watchlist',icon:Bookmark,group:'MANAGE'},
 {label:'Data sources',icon:Database,group:'MANAGE'},
 {label:'Reports',icon:Activity,group:'MANAGE'},
 {label:'Settings',icon:Settings,group:'SYSTEM'}
]
const primaryLabels = new Set<Page>(['Overview','Products','Data sources','Reports','Settings'])
const fmtCompact = (n:number) => n>=1000000 ? `₦${(n/1000000).toFixed(1)}m` : n>=1000 ? `₦${Math.round(n/1000)}k` : money(n)

type BackendState = {loading:boolean;error:string;overview:MarketOverview|null;listings:ApiListing[]}
type DataMode = 'live' | 'imported' | 'demo' | 'empty'

function sourceStatus(source:MarketplaceSource):{label:string;tone:'status-active'|'status-pending'} {
 if(source.enabled&&source.connector_available)return {label:'Enabled',tone:'status-active'}
 if(source.enabled)return {label:'Enabled · connector pending',tone:'status-pending'}
 if(source.permission_status==='approved')return {label:'Approved · connector pending',tone:'status-pending'}
 return {label:'Not enabled',tone:'status-pending'}
}

function imageForLiveCategory(category:string):string {
 const name=category.toLowerCase()
 if(name.includes('phone')||name.includes('tablet'))return 'ðŸ“±'
 if(name.includes('computer')||name.includes('laptop'))return 'ðŸ’»'
 if(name.includes('game'))return 'ðŸŽ®'
 if(name.includes('camera'))return 'ðŸ“·'
 if(name.includes('home'))return 'ðŸ '
 return 'ðŸ“¦'
}
function apiListingToProduct(listing:ApiListing):Product {
 const stamp=/([zZ]|[+-]\d\d:\d\d)$/.test(listing.last_observed_at)?listing.last_observed_at:`${listing.last_observed_at}Z`
 const observed=new Date(stamp)
 return {id:listing.id,title:listing.title,category:listing.category,price:listing.asking_price,previousPrice:listing.asking_price,location:listing.location,source:listing.source_name,condition:listing.condition||'Not provided',listed:Number.isNaN(observed.valueOf())?'Recently observed':observed.toLocaleString(),views:0,saves:0,trend:0,image:stableCategoryMarker(listing.category),description:listing.description||'Live listing collected from an approved marketplace source.',verifiedDemo:false,origin:'live',sourceUrl:listing.source_url||undefined,observedAt:stamp}
}

function stableCategoryMarker(category:string):string {
 const name=category.toLowerCase()
 if(name.includes('phone')||name.includes('tablet'))return 'PH'
 if(name.includes('computer')||name.includes('laptop'))return 'PC'
 if(name.includes('game'))return 'GM'
 if(name.includes('camera'))return 'CA'
 if(name.includes('home'))return 'HM'
 return name.match(/[a-z0-9]/g)?.slice(0,2).join('').toUpperCase()||'IT'
}

function isProduct(value: unknown): value is Product {
 return typeof value === 'object' && value !== null && 'id' in value && typeof value.id === 'number' && 'title' in value && typeof value.title === 'string'
}
function isWorkspaceSettings(value: unknown): value is WorkspaceSettings {
 if(typeof value!=='object'||value===null)return false
 const candidate=value as Partial<WorkspaceSettings>
 return (candidate.defaultMarket==='Nigeria'||candidate.defaultMarket==='Lagos State'||candidate.defaultMarket==='Abuja FCT')&&candidate.currency==='NGN'&&typeof candidate.compactMode==='boolean'&&typeof candidate.weeklyDigest==='boolean'
}
function isPriceAlerts(value: unknown): value is Record<string, number> {
 return typeof value==='object'&&value!==null&&Object.values(value).every(item=>typeof item==='number'&&Number.isFinite(item)&&item>0)
}

function App(){
 const [page,setPage]=useState<Page>('Overview')
 const [mobileOpen,setMobileOpen]=useState(false)
 const [importedDataset,setImportedDataset]=useState(()=>readStored('marketpulse.imported',false,isBoolean))
 const [listings,setListings]=useState<Product[]>(()=>{
  const imported=readStored('marketpulse.imported',false,isBoolean)
  return imported?readStored('marketpulse.listings',[],isArrayOf(isProduct)):[]
 })
 const [liveAvailable,setLiveAvailable]=useState(false)
 const [backendState,setBackendState]=useState<BackendState>({loading:true,error:'',overview:null,listings:[]})
 const [query,setQuery]=useState('')
 const [category,setCategory]=useState('All categories')
 const [location,setLocation]=useState('All Nigeria')
 const [sort,setSort]=useState('Most relevant')
 const [saved,setSaved]=useState<number[]>(()=>readStored('marketpulse.watchlist',[],isNumberArray))
 const [priceAlerts,setPriceAlerts]=useState<Record<string,number>>(()=>readStored('marketpulse.priceAlerts',{},isPriceAlerts))
 const [selected,setSelected]=useState<Product|null>(null)
 const [notice,setNotice]=useState('')
 const [report,setReport]=useState(false)
 const [exporting,setExporting]=useState<'csv'|'pdf'|null>(null)
 const [analysis,setAnalysis]=useState<{text:string;model:string}|null>(null)
 const [localAnalysis,setLocalAnalysis]=useState<{text:string;model:string}|null>(null)
 const [analysisLoading,setAnalysisLoading]=useState(false)
 const [analysisError,setAnalysisError]=useState('')
 const [analysisConsent,setAnalysisConsent]=useState(false)
 const [analysisStatus,setAnalysisStatus]=useState<{configured:boolean;model:string|null}>({configured:false,model:null})
 const [settings,setSettings]=useState<WorkspaceSettings>(()=>readStored('marketpulse.settings',{defaultMarket:'Nigeria',currency:'NGN',compactMode:false,weeklyDigest:false},isWorkspaceSettings))

 const liveProducts=useMemo(()=>backendState.listings.map(apiListingToProduct),[backendState.listings])
 const dataMode:DataMode=importedDataset?'imported':liveAvailable?'live':listings.some(product=>product.verifiedDemo)?'demo':'empty'
 const visibleListings=useMemo(()=>dataMode==='imported'||dataMode==='demo'?listings:dataMode==='live'?liveProducts:[],[dataMode,listings,liveProducts])
 const filtered=useMemo(()=>visibleListings.filter(p=>(category==='All categories'||p.category===category)&&(location==='All Nigeria'||p.location.toLowerCase().includes(location.toLowerCase()))&&([p.title,p.category,p.location,p.source,p.condition].some(value=>value.toLowerCase().includes(query.toLowerCase())))).sort((a,b)=>sort==='Price: low to high'?a.price-b.price:sort==='Price: high to low'?b.price-a.price:sort==='Most viewed'?b.views-a.views:sort==='Most relevant'?(b.views+b.saves)-(a.views+a.saves):b.trend-a.trend),[visibleListings,query,category,location,sort])
 const trendCount=visibleListings.filter(product=>product.trend>0).length
 const notify=(s:string)=>{setNotice(s);window.setTimeout(()=>setNotice(''),3000)}
 const refreshBackend=useCallback(async()=>{
  setBackendState(current=>({...current,loading:true,error:''}))
  try{
   const [overview,recent]=await Promise.all([getMarketOverview(),getRecentListings(50)])
   setBackendState({loading:false,error:'',overview,listings:recent.items})
   setLiveAvailable(true)
  }catch(error){
   setBackendState(current=>({...current,loading:false,error:error instanceof TypeError?`Could not reach ${API_BASE_URL}. Start the backend and check CORS settings.`:error instanceof Error?error.message:'Could not load backend market data.'}))
  }
 },[])
 const toggleSave=(id:number)=>setSaved(old=>{const next=old.includes(id)?old.filter(x=>x!==id):[...old,id];if(!writeStored('marketpulse.watchlist',next))notify('Could not save your watchlist in browser storage.');return next})
 const setPriceAlert=(id:number,threshold:number|null)=>{setPriceAlerts(old=>{const next={...old};if(threshold===null)delete next[String(id)];else next[String(id)]=threshold;if(!writeStored('marketpulse.priceAlerts',next))notify('Could not save your price alert in browser storage.');return next})}
 const go=(p:Page)=>{setPage(p);setMobileOpen(false);setSelected(null)}
 const pageTitle=page==='Overview'?'Market overview':page
 const pageSub:Record<Page,string>={'Overview':'Explore calculated statistics from the listings in your workspace.','Products':'Search and compare records in the current dataset.','Trending':'Review records with a source-provided momentum value.','Price intelligence':'Compare asking prices; no transaction history is implied.','Opportunities':'Review observed asking-price reductions, not profit predictions.','Watchlist':'Keep important listings close in this browser.','Data sources':'Import authorized data and review source limitations.','Reports':'Download a data-backed snapshot of the current dataset.','Settings':'Manage your workspace preferences.'}
 const importFile=async(file:File)=>{try{if(file.size>10_000_000)throw new Error('This CSV is larger than 10 MB. Split it into smaller imports.');const imported=parseListingsCsv(await file.text());if(!window.confirm(`Import ${imported.length} listings and replace the current dataset?`))return;if(!writeStored('marketpulse.listings',imported)||!writeStored('marketpulse.imported',true)||!writeStored('marketpulse.watchlist',[])||!writeStored('marketpulse.priceAlerts',{}))throw new Error('The browser storage limit was reached.');setListings(imported);setImportedDataset(true);setSaved([]);setPriceAlerts({});setReport(false);setAnalysis(null);setLocalAnalysis(null);setAnalysisError('');setAnalysisConsent(false);setQuery('');setCategory('All categories');setLocation('All Nigeria');notify(`Imported ${imported.length} listings. Data stays in this browser.`)}catch(error){const message=error instanceof Error?error.message:'Could not read this CSV file.';notify(`Import failed: ${message}`)}}
 const restoreDemo=()=>{if(!writeStored('marketpulse.listings',demoProducts)||!writeStored('marketpulse.imported',false)||!writeStored('marketpulse.watchlist',[])||!writeStored('marketpulse.priceAlerts',{})){notify('Could not save this change in browser storage.');return}setListings(demoProducts);setImportedDataset(false);setSaved([]);setPriceAlerts({});setReport(false);setAnalysis(null);setLocalAnalysis(null);setAnalysisError('');setAnalysisConsent(false);setQuery('');setCategory('All categories');setLocation('All Nigeria');notify('Demonstration dataset restored.')}
 const download=(filename:string,content:string,type:string)=>{const blob=new Blob([content],{type});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)}
 const exportListings=async(format:'csv'|'pdf',asReport=false)=>{
  if(exporting)return
  setExporting(format)
  try{
   let rows=dataMode==='live'?(await getExportListings()).map(apiListingToProduct):visibleListings
   let scope=dataMode==='live'?'All collected market records':dataMode==='imported'?'User-imported dataset':'Demonstration dataset'
   if(page==='Products'){
    rows=rows.filter(p=>(category==='All categories'||p.category===category)&&(location==='All Nigeria'||p.location.toLowerCase().includes(location.toLowerCase()))&&[p.title,p.category,p.location,p.source,p.condition].some(value=>value.toLowerCase().includes(query.toLowerCase())))
    scope+=` | Filters: ${category}; ${location}; search ${query||'all products'}`
   }else if(page==='Watchlist'){
    rows=rows.filter(p=>saved.includes(p.id))
    scope+=' | Watchlist'
   }
   if(!rows.length)throw new Error('There are no matching records to export yet.')
   const day=new Date().toISOString().slice(0,10)
   if(format==='pdf'){
    if(rows.length>5000)throw new Error('PDF exports support up to 5,000 records. Filter the Products page or use CSV for the full dataset.')
    const {downloadMarketPdf}=await import('./pdf')
    downloadMarketPdf(rows,scope,`marketpulse-report-${day}.pdf`)
   }else download(`marketpulse-listings-${day}.csv`,'\uFEFF'+toCsv(rows),'text/csv;charset=utf-8')
   if(asReport)setReport(true)
   notify(`Exported ${rows.length.toLocaleString()} records as ${format.toUpperCase()}, ordered by category and product name.`)
  }catch(error){notify(error instanceof Error?error.message:'Could not prepare the export. Please try again.')}
  finally{setExporting(null)}
 }
 const exportReport=()=>{void exportListings('pdf',true)}
 const downloadTemplate=()=>download('marketpulse-import-template.csv','title,category,price,location,source,previous_price,condition,listed,views,saves,trend,description\r\n','text/csv;charset=utf-8')
 const analyzeLocally=()=>{setLocalAnalysis(buildLocalAnalysis(visibleListings));setAnalysisError('')}
 const analyzeDataset=async()=>{setAnalysis(null);setAnalysisError('');setAnalysisLoading(true);try{const payload:MarketAnalysisPayload=buildAnalysisPayload(visibleListings);const response=await fetch(`${API_BASE_URL}/api/analysis`,{method:'POST',headers:{'Content-Type':'application/json',...(API_READ_TOKEN?{Authorization:`Bearer ${API_READ_TOKEN}`}:{})},body:JSON.stringify(payload)});const result=await response.json() as {analysis?:unknown;model?:unknown;detail?:unknown};if(!response.ok){const detail=typeof result.detail==='string'?result.detail:Array.isArray(result.detail)?result.detail.map(item=>typeof item==='object'&&item!==null&&'msg'in item?String(item.msg):'').filter(Boolean).join('; '):'';throw new Error(detail||`Analysis request failed (${response.status}).`)}if(typeof result.analysis!=='string'||typeof result.model!=='string')throw new Error('The analysis service returned an unexpected response.');setAnalysis({text:result.analysis,model:result.model})}catch(error){const message=error instanceof TypeError?`Could not reach the MarketPulse API at ${API_BASE_URL}. Start the backend and check CORS settings.`:error instanceof Error?error.message:'AI analysis failed unexpectedly.';setAnalysisError(message)}finally{setAnalysisLoading(false)}}
 const updateSettings=(next:WorkspaceSettings)=>{setSettings(next);if(!writeStored('marketpulse.settings',next))notify('Could not save workspace preferences in browser storage.')}
 useEffect(()=>{void getAnalysisStatus().then(status=>setAnalysisStatus({configured:status.configured,model:status.model})).catch(()=>setAnalysisStatus({configured:false,model:null}))},[])
 useEffect(()=>{void refreshBackend()},[refreshBackend])
 useEffect(()=>{
  const handleShortcut=(event:KeyboardEvent)=>{
   if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){
    event.preventDefault()
    document.querySelector<HTMLInputElement>('input[aria-label="Search products"]')?.focus()
   }
  }
  window.addEventListener('keydown',handleShortcut)
  return ()=>window.removeEventListener('keydown',handleShortcut)
 },[])

  return <div className={`app-shell ${settings.compactMode?'compact-mode':''} ${dataMode}-mode`}>
  {mobileOpen&&<div className="mobile-scrim" onClick={()=>setMobileOpen(false)} />}
  <aside className={`sidebar ${mobileOpen?'sidebar-open':''}`}>
   <div className="brand"><div className="brand-mark"><Activity size={20}/></div><div><b>market<span>pulse</span></b><small>NIGERIA INTELLIGENCE</small></div><button aria-label="Close navigation" className="icon-btn close-nav" onClick={()=>setMobileOpen(false)}><X size={18}/></button></div>
   <div className="workspace-switch"><div className="workspace-avatar">MP</div><div><b>My workspace</b><small>Personal research</small></div><ChevronDown size={15}/></div>
   {['WORKSPACE','MANAGE','SYSTEM'].map(group=><div className="nav-group" key={group}><p>{group}</p>{nav.filter(n=>n.group===group&&primaryLabels.has(n.label)).map(n=><button key={n.label} onClick={()=>go(n.label)} className={`nav-item ${page===n.label?'active':''}`}><n.icon size={17}/><span>{n.label}</span></button>)}</div>)}
   <div className="nav-group nav-more"><p>MORE TOOLS</p>{nav.filter(n=>!primaryLabels.has(n.label)).map(n=><button key={n.label} onClick={()=>go(n.label)} className={`nav-item ${page===n.label?'active':''}`}><n.icon size={17}/><span>{n.label}</span>{n.label==='Trending'&&trendCount>0&&<i className="nav-count">{trendCount}</i>}</button>)}</div>
   <div className="sidebar-bottom"><div className="source-health"><div className="health-icon"><ShieldCheck size={17}/></div><div><b>Data status</b><small>{dataMode==='live'?'Live Jiji data':dataMode==='imported'?'Imported data':dataMode==='demo'?'Demo fallback':'Waiting for data'}</small></div><span className="green-dot"/></div><div className="profile"><div className="profile-avatar">A</div><div><b>Arlo workspace</b><small>Local preview</small></div><MoreHorizontal size={18}/></div></div>
  </aside>
  <main className="main-area">
   <header className="topbar"><button aria-label="Open navigation" className="icon-btn mobile-menu" onClick={()=>setMobileOpen(true)}><Menu/></button><div className="crumb"><span>Workspace</span><b>/</b><strong>{page}</strong></div><div className="top-actions"><div className="top-search"><Search size={15}/><input aria-label="Search products" placeholder="Search products, categories or locations..." value={query} onChange={e=>{setQuery(e.target.value);if(page!=='Products')setPage('Products')}}/><kbd>Ctrl K</kbd></div><button aria-label="Show notifications" className="icon-btn notification" onClick={()=>notify('Notifications are not configured for this local workspace.')}><Bell size={18}/><i/></button><div className="top-avatar">A</div></div></header>
   <div className="content">
    <div className="page-heading"><div><div className="eyebrow"><span className="pulse-dot"/> MARKET INTELLIGENCE <span className="demo-tag">{dataMode==='live'?'LIVE DATA':dataMode==='imported'?'IMPORTED DATA':dataMode==='demo'?'DEMO DATA':'NO DATA'}</span></div><h1>{pageTitle}</h1><p>{pageSub[page]}</p></div><div className="heading-actions">{page==='Overview'&&<span className="select compact">{dataMode==='live'&&backendState.overview?backendState.overview.active_listings.toLocaleString():visibleListings.length} listings</span>}<button className="btn btn-secondary" onClick={()=>void exportListings('csv')} disabled={!visibleListings.length||exporting!==null}><Download size={15}/>{exporting==='csv'?'Preparing CSV...':'Export CSV'}</button><button className="btn btn-secondary" onClick={()=>void exportListings('pdf')} disabled={!visibleListings.length||exporting!==null}><Download size={15}/>{exporting==='pdf'?'Preparing PDF...':'Export PDF'}</button><button className="btn btn-primary" onClick={()=>go('Data sources')}><Upload size={15}/> Import data</button></div></div>
    <div className="demo-banner"><span><CircleHelp size={16}/></span><div><b>{dataMode==='live'?'Live Jiji data is connected.':dataMode==='imported'?'You’re viewing user-imported data.':dataMode==='demo'?'You’re viewing demonstration data.':'No market dataset is connected yet.'}</b> {dataMode==='live'?(backendState.overview?`${backendState.overview.active_listings.toLocaleString()} active records are available in the backend; the workspace shows the latest collected rows.`:'The backend is loading collected records.') :dataMode==='imported'?'Imported records are not independently verified.':dataMode==='demo'?'Demo records are only for testing the interface.':'Start the backend to load approved Jiji records, or import a CSV file.'}</div><button onClick={()=>go(dataMode==='empty'?'Data sources':'Products')}>{dataMode==='empty'?'Connect data':'View listings'} <ExternalLink size={13}/></button></div>

     {page==='Overview'&&<><BackendObservations state={backendState} onRefresh={refreshBackend}/>{dataMode==='empty'?null:<Overview listings={visibleListings} go={go} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/>}</>}
     {page==='Products'&&<ProductsView listings={visibleListings} filtered={filtered} query={query} setQuery={setQuery} category={category} setCategory={setCategory} location={location} setLocation={setLocation} sort={sort} setSort={setSort} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/>}
     {page==='Trending'&&<TrendingView listings={visibleListings} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/>}
     {page==='Price intelligence'&&<PriceView listings={visibleListings} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/>}
    {page==='Opportunities'&&<OpportunityView listings={visibleListings} setSelected={setSelected}/>}
     {page==='Watchlist'&&<WatchlistView listings={visibleListings} saved={saved} priceAlerts={priceAlerts} toggleSave={toggleSave} setSelected={setSelected}/>}
    {page==='Data sources'&&<SourcesView importFile={importFile} importedDataset={importedDataset} dataMode={dataMode} restoreDemo={restoreDemo} listingsCount={visibleListings.length} downloadTemplate={downloadTemplate}/>}
     {page==='Reports'&&<ReportsView report={report} onGenerate={exportReport} importedDataset={importedDataset||dataMode==='live'} analysis={analysis} localAnalysis={localAnalysis} analysisLoading={analysisLoading} analysisError={analysisError} analysisConsent={analysisConsent} setAnalysisConsent={setAnalysisConsent} onAnalyze={analyzeDataset} onAnalyzeLocally={analyzeLocally} openAiConfigured={analysisStatus.configured} openAiModel={analysisStatus.model}/>}
     {page==='Settings'&&<SettingsView settings={settings} onChange={updateSettings} notify={notify}/>}
    <footer><span>© 2026 MarketPulse</span><span><i className="green-dot"/> {dataMode==='live'?'Live Jiji data':dataMode==='imported'?'Imported dataset':dataMode==='demo'?'Demo fallback':'No data connected'}</span><span>Built for Nigeria's resale economy</span></footer>
   </div>
  </main>
   {selected&&<ProductModal product={selected} saved={saved.includes(selected.id)} alertThreshold={priceAlerts[String(selected.id)]??null} onSave={()=>toggleSave(selected.id)} onSetAlert={threshold=>setPriceAlert(selected.id,threshold)} onClose={()=>setSelected(null)}/>}
  {notice&&<div className="toast"><span>✓</span>{notice}</div>}
 </div>
}

function BackendObservations({state,onRefresh}:{state:BackendState;onRefresh:()=>void}){
 const refresh=onRefresh
 if(state.loading&&!state.overview)return <section className="panel backend-observations"><div className="panel-head"><div><span className="eyebrow">DATABASE OBSERVATIONS</span><h3>Loading collected market data…</h3></div></div></section>
 if(!state.overview)return <section className="panel backend-observations"><div className="panel-head"><div><span className="eyebrow">DATABASE OBSERVATIONS</span><h3>Backend market data unavailable</h3></div><button className="btn btn-secondary" onClick={()=>void refresh()} disabled={state.loading}>{state.loading?'Refreshing…':'Retry'}</button></div><div className="analysis-error" role="alert">{state.error}</div></section>

 const overview=state.overview
 const categories=overview.categories.slice(0,10)
 return <section className="backend-observations">
  <div className="panel backend-observations-head"><div><span className="eyebrow">DATABASE OBSERVATIONS · NOT DEMO DATA</span><h2>Collected market records</h2><p>Backend-derived figures from approved source data. Listing activity is a supply signal, not buyer demand.</p></div><button className="btn btn-secondary" onClick={()=>void refresh()} disabled={state.loading}>{state.loading?'Refreshing…':'Refresh'}</button></div>
  {state.error&&<div className="analysis-error" role="alert">{state.error} Showing the last successfully loaded data.</div>}
  <section className="metrics-grid">
   <Metric label="Active database listings" value={overview.active_listings.toLocaleString()} note={`${overview.total_listings.toLocaleString()} total tracked`} icon={Boxes} tone="blue"/>
   <Metric label="Median asking price" value={overview.median_asking_price_ngn?fmtCompact(overview.median_asking_price_ngn):'—'} note="active listings · not sale prices" icon={Gauge} tone="violet"/>
   <Metric label="Observed price reductions" value={overview.price_reductions.toLocaleString()} note="based on consecutive observations" icon={ArrowDownRight} tone="amber"/>
   <Metric label="Enabled authorized sources" value={overview.enabled_sources.toLocaleString()} note={overview.latest_collection_at?`Last successful collection ${new Date(overview.latest_collection_at).toLocaleString()}`:'No successful collection yet'} icon={Database} tone="green"/>
  </section>
  {overview.active_listings===0?<div className="panel empty-state"><Database size={25}/><b>No active listing records are currently available.</b><span>Check source approvals, collection runs, and listing filters. Backend data remains separate from the local demo or imported workspace dataset.</span></div>:<>
   <section className="overview-grid">
    <div className="panel chart-panel"><div className="panel-head"><div><h3>Median asking price by category</h3><p>Computed from active database records</p></div></div>{categories.length?<div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={categories} layout="vertical" margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid strokeDasharray="3 5" horizontal={false} stroke="#edf0f5"/><XAxis type="number" tickFormatter={fmtCompact} axisLine={false} tickLine={false} tick={{fill:'#8b95a7',fontSize:10}}/><YAxis type="category" dataKey="category" axisLine={false} tickLine={false} width={110} tick={{fill:'#68758a',fontSize:10}}/><Tooltip formatter={value=>money(Number(value))}/><Bar dataKey="median_asking_price_ngn" fill="#5c83ec" radius={[0,5,5,0]} barSize={15}/></BarChart></ResponsiveContainer></div>:<div className="empty-state">No category statistics available.</div>}</div>
    <div className="panel category-panel"><div className="panel-head"><div><h3>Recent active listings</h3><p>Latest records observed by the backend</p></div></div>{state.listings.length?<div className="recent-listings">{state.listings.map(listing=><div className="recent-listing" key={listing.id}><div><b>{listing.title}</b><small>{listing.category} · {listing.location} · {listing.source_name}</small></div><strong>{money(listing.asking_price)}</strong>{listing.source_url&&<a href={listing.source_url} target="_blank" rel="noreferrer" aria-label={`Open source listing for ${listing.title}`}><ExternalLink size={14}/></a>}</div>)}</div>:<div className="empty-state"><span>No active listing rows found.</span></div>}</div>
   </section>
   <section className="panel table-panel"><div className="panel-head"><div><h3>Listing activity by category</h3><p>Newly observed records in adjacent seven-day windows</p></div><span className="status-pill status-demo">Supply signal only</span></div>{overview.listing_momentum.length?<div className="momentum-list">{overview.listing_momentum.slice(0,8).map(item=><div className="source-detail" key={item.category}><span><b>{item.category}</b><small>{item.current_7_day_listings} recent · {item.previous_7_day_listings} previous</small></span><strong>{item.change_percent===null?'No prior baseline':`${item.change_percent>0?'+':''}${item.change_percent}%`}</strong></div>)}</div>:<div className="empty-state">Not enough history for a listing-activity comparison.</div>}</section>
  </>}
  <div className="callout-note"><CircleHelp size={17}/><span>{overview.limitations.join(' ')}</span></div>
 </section>
}

function Overview({listings,go,setSelected,saved,toggleSave}:{listings:Product[];go:(p:Page)=>void;setSelected:(p:Product)=>void;saved:number[];toggleSave:(id:number)=>void}){
 const categories=Object.entries(listings.reduce<Record<string,Product[]>>((groups,product)=>{(groups[product.category]??=[]).push(product);return groups},{}))
 const categoryCounts=categories.map(([name,items])=>({name,value:items.length})).sort((a,b)=>b.value-a.value)
 const categoryPrices=categories.map(([name,items])=>({name,price:median(items.map(product=>product.price)),count:items.length})).sort((a,b)=>b.price-a.price)
 const sourceNames=Array.from(new Set(listings.map(product=>product.source))).slice(0,2)
 const medianPrice=median(listings.map(product=>product.price))
 const reductions=listings.filter(product=>product.previousPrice>product.price).length
 const withEngagement=listings.filter(product=>product.views>0||product.saves>0).length
 const activeListings=[...listings].sort((a,b)=>(b.views+b.saves)-(a.views+a.saves)).slice(0,5)
 return <>
  <section className="metrics-grid">
   <Metric label="Listings in dataset" value={listings.length.toLocaleString()} note="current workspace" icon={Boxes} tone="blue"/>
   <Metric label="Median asking price" value={medianPrice?fmtCompact(medianPrice):'—'} note="across available listings" icon={Gauge} tone="violet"/>
   <Metric label="Price reductions" value={reductions.toLocaleString()} note="current ask below previous ask" icon={ArrowDownRight} tone="amber"/>
   <Metric label="Rows with engagement" value={withEngagement.toLocaleString()} note="views or saves provided" icon={Activity} tone="green"/>
  </section>
  <section className="overview-grid">
   <div className="panel chart-panel"><div className="panel-head"><div><h3>Median asking price by category</h3><p>Computed from the current dataset · asking price, not sale price</p></div></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={categoryPrices} layout="vertical" margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid strokeDasharray="3 5" horizontal={false} stroke="#edf0f5"/><XAxis type="number" tickFormatter={fmtCompact} axisLine={false} tickLine={false} tick={{fill:'#8b95a7',fontSize:10}}/><YAxis type="category" dataKey="name" axisLine={false} tickLine={false} width={100} tick={{fill:'#68758a',fontSize:10}}/><Tooltip formatter={(value)=>money(Number(value))} contentStyle={{border:'1px solid #edf0f5',borderRadius:12,fontSize:12}}/><Bar dataKey="price" fill="#5c83ec" radius={[0,5,5,0]} barSize={15}/></BarChart></ResponsiveContainer></div></div>
   <div className="panel category-panel"><div className="panel-head"><div><h3>Listing coverage</h3><p>Records by category</p></div></div><div className="category-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={categoryCounts} layout="vertical" margin={{top:4,right:12,left:0,bottom:0}}><CartesianGrid strokeDasharray="3 5" horizontal={false} stroke="#edf0f5"/><XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} tick={{fill:'#8b95a7',fontSize:10}}/><YAxis type="category" dataKey="name" axisLine={false} tickLine={false} width={100} tick={{fill:'#68758a',fontSize:10}}/><Tooltip/><Bar dataKey="value" fill="#5c83ec" radius={[0,5,5,0]} barSize={13}/></BarChart></ResponsiveContainer></div><div className="category-foot"><span>Categories represented</span><b>{categoryCounts.length}</b></div></div>
  </section>
  <section className="panel table-panel"><div className="panel-head"><div><h3>Listings with reported engagement</h3><p>Sorted by available views and saves; not a demand measure</p></div><button className="text-btn" onClick={()=>go('Products')}>Explore listings <ArrowUpRight size={14}/></button></div><ProductTable items={activeListings} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/></section>
  <section className="bottom-grid"><div className="panel insight-panel"><div className="insight-icon"><Sparkles size={18}/></div><div><span className="eyebrow">DATASET SNAPSHOT</span><h3>{categoryCounts[0]?`${categoryCounts[0].name} leads listing coverage`:'No listings loaded'}</h3><p>{categoryCounts[0]?`${categoryCounts[0].value} of ${listings.length} records are in the most represented category. Listing volume is not a measure of buyer demand.`:'Import an authorized CSV export to start analyzing observed listings.'}</p><button className="text-btn" onClick={()=>go('Opportunities')}>Review price changes <ArrowUpRight size={14}/></button></div></div><div className="panel mini-source"><div className="panel-head"><div><h3>Source coverage</h3><p>Sources named in this dataset</p></div><button className="text-btn" onClick={()=>go('Data sources')}>Manage</button></div>{sourceNames.length?sourceNames.map((source,index)=><div className="source-row" key={source}><span className={`source-logo ${index?'orange':''}`}>{source.slice(0,1).toUpperCase()}</span><div><b>{source}</b><small>{listings.filter(product=>product.source===source).length} listing records</small></div><span className="status-pill status-demo">{listings.some(product=>product.source===source&&product.verifiedDemo)?'Demo':'Imported'}</span></div>):<div className="empty-state"><Database size={22}/><span>No source fields in this dataset.</span></div>}</div></section>
 </>
}
function ProductsView({listings,filtered,query,setQuery,category,setCategory,location,setLocation,sort,setSort,setSelected,saved,toggleSave}:{listings:Product[];filtered:Product[];query:string;setQuery:(s:string)=>void;category:string;setCategory:(s:string)=>void;location:string;setLocation:(s:string)=>void;sort:string;setSort:(s:string)=>void;setSelected:(p:Product)=>void;saved:number[];toggleSave:(id:number)=>void}){
 const categoryOptions=['All categories',...Array.from(new Set(listings.map(product=>product.category))).sort()]
 const locationOptions=['All Nigeria',...new Set([...locations.slice(1,-1),...listings.map(product=>product.location)])]
  return <div className="panel explorer-panel"><div className="explorer-toolbar"><div className="search-field"><Search size={16}/><input aria-label="Search products in dataset" placeholder="Search products, brands or keywords..." value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<button aria-label="Clear product search" onClick={()=>setQuery('')}><X size={14}/></button>}</div><div className="filter-label"><SlidersHorizontal size={15}/> Filters</div><select aria-label="Filter by category" className="select" value={category} onChange={e=>setCategory(e.target.value)}>{categoryOptions.map(c=><option key={c}>{c}</option>)}</select><select aria-label="Filter by location" className="select" value={location} onChange={e=>setLocation(e.target.value)}>{locationOptions.map(l=><option key={l}>{l}</option>)}</select><select aria-label="Sort listings" className="select" value={sort} onChange={e=>setSort(e.target.value)}><option>Most relevant</option><option>Most viewed</option><option>Price: low to high</option><option>Price: high to low</option></select></div><div className="results-line"><span><b>{filtered.length}</b> listings found</span><span><Filter size={13}/> {filtered.some(p=>p.verifiedDemo)?'Includes demo records':'Current dataset'}</span></div><div className="product-grid">{filtered.map(p=><ProductCard key={p.id} product={p} setSelected={setSelected} saved={saved.includes(p.id)} toggleSave={toggleSave}/>)}</div>{filtered.length===0&&<div className="empty-state"><PackageSearch size={28}/><b>No matching products</b><span>Try changing your search or filters.</span></div>}</div>
}
function TrendingView({listings,setSelected,saved,toggleSave}:{listings:Product[];setSelected:(p:Product)=>void;saved:number[];toggleSave:(id:number)=>void}){
 const sorted=[...listings].filter(product=>product.trend>0).sort((a,b)=>b.trend-a.trend)
 return <><div className="section-intro"><div><h3>Listings with a reported momentum value</h3><p>Sorted by the trend field in your dataset; blank/zero values are not ranked.</p></div><span className="status-pill status-demo">{sorted.length} ranked</span></div><div className="panel table-panel">{sorted.length?<ProductTable items={sorted} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/>:<div className="empty-state"><TrendingUp size={28}/><b>No trend observations available</b><span>Import records with a source-provided trend field to rank listings.</span></div>}</div><div className="callout-note"><CircleHelp size={17}/><span>Trend values require reliable repeated observations. They are not a measure of demand unless supported by source data.</span></div></>
}
function PriceView({listings,setSelected,saved,toggleSave}:{listings:Product[];setSelected:(p:Product)=>void;saved:number[];toggleSave:(id:number)=>void}){
 const categories=Object.entries(listings.reduce<Record<string,Product[]>>((groups,product)=>{(groups[product.category]??=[]).push(product);return groups},{}))
 const categoryPrices=categories.map(([name,items])=>({name,price:median(items.map(product=>product.price)),count:items.length})).sort((a,b)=>a.price-b.price)
 const reductions=listings.filter(product=>product.previousPrice>product.price).length
 const increases=listings.filter(product=>product.previousPrice>0&&product.price>product.previousPrice).length
 return <><div className="metrics-grid three"><Metric label="Median asking price" value={listings.length?fmtCompact(median(listings.map(product=>product.price))):'—'} note="current dataset" icon={Gauge} tone="blue"/><Metric label="Price reductions" value={reductions.toLocaleString()} note="current ask below previous ask" icon={ArrowDownRight} tone="green"/><Metric label="Price increases" value={increases.toLocaleString()} note="current ask above previous ask" icon={ArrowUpRight} tone="amber"/></div><div className="panel chart-panel tall"><div className="panel-head"><div><h3>Median asking price by category</h3><p>Each value is derived from the current dataset; not transaction history.</p></div><span className="status-pill status-demo">{listings.length} listings</span></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={categoryPrices} layout="vertical" margin={{top:8,right:18,left:4,bottom:0}}><CartesianGrid strokeDasharray="3 5" horizontal={false} stroke="#edf0f5"/><XAxis type="number" tickFormatter={fmtCompact} axisLine={false} tickLine={false} tick={{fill:'#8b95a7',fontSize:10}}/><YAxis type="category" dataKey="name" axisLine={false} tickLine={false} width={110} tick={{fill:'#68758a',fontSize:10}}/><Tooltip formatter={value=>money(Number(value))}/><Bar dataKey="price" fill="#4779ed" radius={[0,5,5,0]} barSize={17}/></BarChart></ResponsiveContainer></div></div><div className="panel table-panel"><div className="panel-head"><div><h3>Comparable asking prices</h3><p>Listings in the current dataset only</p></div></div><ProductTable items={listings} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/></div></>
}
function OpportunityView({listings,setSelected}:{listings:Product[];setSelected:(p:Product)=>void}){
 const reductions=listings.filter(p=>p.previousPrice>p.price).sort((a,b)=>(b.previousPrice-b.price)-(a.previousPrice-a.price))
 return <><div className="opportunity-summary"><div className="opportunity-symbol"><Sparkles size={22}/></div><div><span className="eyebrow">PRICE-CHANGE SCREEN</span><h2>{reductions.length} observed price reduction{reductions.length===1?'':'s'}</h2><p>Ranked by absolute change between current and previous asking prices in the imported or demo records. This is not a profit or demand estimate.</p></div></div><div className="opportunity-grid">{reductions.map(p=>{const change=p.previousPrice-p.price;const percent=Math.round(change/p.previousPrice*100);return <div className="panel opportunity-card" key={p.id}><div className="opp-top"><span className="category-chip">{p.category}</span><span className="opportunity-score">Ask down {percent}%</span></div><div className="opp-product"><span>{p.image}</span><div><b>{p.title}</b><small>{p.location}</small></div></div><div className="opp-prices"><div><small>Current ask</small><b>{money(p.price)}</b></div><div><small>Previous ask</small><b>{money(p.previousPrice)}</b></div><div className="saving"><small>Observed ask change</small><b>-{money(change)}</b></div></div><p className="opp-disclaimer">Price change only. Verify timing, condition and all costs independently.</p><button className="view-listing" onClick={()=>setSelected(p)}>Inspect listing <ArrowUpRight size={14}/></button></div>})}{reductions.length===0&&<div className="empty-state"><Gauge size={28}/><b>No recorded price reductions</b><span>Import listings with a previous_price column to screen price changes.</span></div>}</div></>
}
function WatchlistView({listings,saved,priceAlerts,toggleSave,setSelected}:{listings:Product[];saved:number[];priceAlerts:Record<string,number>;toggleSave:(id:number)=>void;setSelected:(p:Product)=>void}){
 const items=listings.filter(p=>saved.includes(p.id))
 const alertCount=items.filter(item=>priceAlerts[String(item.id)]!==undefined).length
 return <div className="panel table-panel"><div className="panel-head"><div><h3>Saved products</h3><p>{items.length} products in your personal watchlist · {alertCount} price alert{alertCount===1?'':'s'}</p></div></div>{items.length?<ProductTable items={items} setSelected={setSelected} saved={saved} toggleSave={toggleSave}/>:<div className="empty-state"><Bookmark size={28}/><b>Your watchlist is empty</b><span>Save products from the explorer to track them here.</span></div>}</div>
}
function SourcesView({importFile,importedDataset,dataMode,restoreDemo,listingsCount,downloadTemplate}:{importFile:(file:File)=>void;importedDataset:boolean;dataMode:DataMode;restoreDemo:()=>void;listingsCount:number;downloadTemplate:()=>void}){
 const [apiState,setApiState]=useState<{loading:boolean;error:string;sources:MarketplaceSource[]}>({loading:true,error:'',sources:[]})
 const refreshApi=async()=>{
  setApiState(current=>({...current,loading:true,error:''}))
  try{
   const [health,sources]=await Promise.all([getApiHealth(),getMarketplaceSources()])
   if(health.status!=='ok'||health.database!=='ok')throw new Error('The API or its database is not healthy.')
   setApiState({loading:false,error:'',sources})
  }catch(error){
   setApiState({loading:false,error:error instanceof TypeError?`Could not reach ${API_BASE_URL}. Start the backend and check CORS settings.`:error instanceof Error?error.message:'Could not load the source catalog.',sources:[]})
  }
 }
 useEffect(()=>{void refreshApi()},[])
 return <>
  <div className="source-intro"><div><div className="source-intro-icon"><Database/></div><h2>Bring in authorized market data</h2><p>Import a CSV export from a source you are permitted to access. CSV files stay in this browser. Server-side collection uses only enabled, approved connectors and never runs in the browser.</p><div className="source-actions"><label className="btn btn-primary csv-upload"><Upload size={15}/> Import listings CSV<input className="csv-file-input" type="file" accept=".csv,text/csv" onChange={event=>{const file=event.target.files?.[0];if(file){void importFile(file);event.target.value=''}}}/></label><button className="btn btn-secondary" onClick={downloadTemplate}><Download size={15}/> Download CSV template</button></div></div></div>
  <div className="source-cards"><div className="panel source-card"><div className="source-card-top"><div className="source-logo large"><Upload/></div><span className="status-pill status-active">Ready</span></div><h3>CSV import</h3><p>Replace the current workspace dataset with normalized listing rows.</p><div className="source-detail"><span>Current dataset</span><b>{dataMode==='live'?'Live Jiji data':dataMode==='imported'?'Imported CSV':dataMode==='demo'?'Demonstration data':'No dataset loaded'}</b></div><div className="source-detail"><span>Listings loaded</span><b>{listingsCount}</b></div><details className="csv-help"><summary>Required columns and supported fields</summary><p>Required: <code>title</code>, <code>category</code>, <code>price</code> (or <code>asking_price</code>), <code>location</code>, and <code>source</code> (or <code>source_name</code>).</p><p>Optional: <code>previous_price</code>, <code>condition</code>, <code>listed</code> (or <code>observed_at</code>), <code>views</code>, <code>saves</code>, <code>trend</code>, and <code>description</code>. Quote comma-containing values such as prices.</p></details>{importedDataset&&<button className="btn btn-secondary full-btn" onClick={restoreDemo}>Restore demonstration dataset</button>}</div></div>
   <section className="panel source-card source-catalog"><div className="source-card-top"><div><h3>Backend source catalog</h3><p>Permission and connector status reported by the configured MarketPulse API.</p></div><button className="btn btn-secondary" onClick={()=>void refreshApi()} disabled={apiState.loading}>{apiState.loading?'Checking…':'Refresh status'}</button></div>{apiState.error&&<div className="analysis-error" role="alert">{apiState.error}</div>}{apiState.loading&&!apiState.sources.length&&!apiState.error&&<p>Checking API and database…</p>}{!apiState.loading&&!apiState.error&&apiState.sources.length===0&&<div className="empty-state"><Database size={22}/><span>No marketplace sources are configured.</span></div>}{apiState.sources.map(source=>{const state=sourceStatus(source);return <div className="source-detail source-catalog-row" key={source.source_key}><span><b>{source.name}</b><small>{source.access_method} · permission {source.permission_status}{source.permission_reference_present?' · reference recorded':''}</small><small>{source.connector_available?'Connector registered':'No connector registered'} · {source.permitted_categories.length?source.permitted_categories.join(', '):'no approved categories'}</small></span><span className={`status-pill ${state.tone}`}>{state.label}</span></div>})}</section>
   {apiState.sources.some(source=>source.permission_status==='approved'&&!source.connector_available)&&<div className="callout-note"><ShieldCheck size={17}/><span>Permission is approved for some sources, but collection remains off until a source-specific connector is registered. This protects your access agreement and prevents unsupported scraping.</span></div>}
   <div className="callout-note"><ShieldCheck size={17}/><span>Respect source terms, rate limits and data-use permissions. The Jiji connector checks robots.txt, stays disabled until explicitly approved, and does not collect seller contact details. Imported data is not independently verified.</span></div>
 </>
}
function ReportsView({report,onGenerate,importedDataset,analysis,localAnalysis,analysisLoading,analysisError,analysisConsent,setAnalysisConsent,onAnalyze,onAnalyzeLocally,openAiConfigured,openAiModel}:{report:boolean;onGenerate:()=>void;importedDataset:boolean;analysis:{text:string;model:string}|null;localAnalysis:{text:string;model:string}|null;analysisLoading:boolean;analysisError:string;analysisConsent:boolean;setAnalysisConsent:(value:boolean)=>void;onAnalyze:()=>void;onAnalyzeLocally:()=>void;openAiConfigured:boolean;openAiModel:string|null}){
 return <><div className="report-hero"><div className="report-hero-icon"><Sparkles size={22}/></div><div><span className="eyebrow">INTELLIGENCE STUDIO</span><h2>Analyze your market dataset.</h2><p>Generate a free local interpretation or optionally ask OpenAI to interpret category-level aggregates.</p></div><button className="btn btn-secondary" onClick={onGenerate}><Download size={15}/> Download snapshot</button></div><section className="panel ai-analysis-panel"><div className="panel-head"><div><h3>Free local analysis</h3><p>Runs in your browser and keeps your data on this device.</p></div><span className="status-pill status-active">No API key</span></div><div className="analysis-actions"><button className="btn btn-primary" onClick={onAnalyzeLocally}><Sparkles size={15}/> Analyze locally</button></div>{localAnalysis&&<AnalysisResult result={localAnalysis} explanation="Rule-based interpretation of your local aggregates and evidence rows."/>}</section><section className="panel ai-analysis-panel"><div className="panel-head"><div><h3>Optional OpenAI analysis</h3><p>Uses only aggregate counts and asking-price summaries from this dataset.</p></div><span className={`status-pill ${openAiConfigured?'status-active':'status-pending'}`}>{openAiConfigured?openAiModel:'Not configured'}</span></div><p className="analysis-privacy">With your consent, category labels and aggregate listing counts, median asking prices, price reductions, and engagement coverage are sent to OpenAI. Individual titles, descriptions, exact locations, source names, and seller details are not included.</p><label className="analysis-consent"><input type="checkbox" checked={analysisConsent} onChange={event=>setAnalysisConsent(event.target.checked)}/> I understand that these aggregate dataset statistics will be sent to OpenAI for analysis.</label><div className="analysis-actions"><button className="btn btn-primary" disabled={!importedDataset||!analysisConsent||!openAiConfigured||analysisLoading} onClick={onAnalyze}>{analysisLoading?<><span className="analysis-spinner"/> Analyzing…</>:<><Sparkles size={15}/> Analyze with OpenAI</>}</button>{!openAiConfigured&&<span>Optional service unavailable; local analysis is free and ready.</span>}</div>{analysisError&&<div className="analysis-error" role="alert">{analysisError}</div>}{analysis&&<AnalysisResult result={analysis} explanation="AI-generated interpretation of aggregates, not verified market facts."/>}</section><div className="report-grid"><div className="panel report-card"><span className="report-icon blue"><TrendingUp/></span><h3>Dataset coverage</h3><p>Snapshot includes listing count and category coverage.</p><small>Calculated from the current workspace</small></div><div className="panel report-card"><span className="report-icon violet"><Gauge/></span><h3>Price snapshot</h3><p>Includes median asking price and observed price reductions.</p><small>Asking prices are not verified transaction prices</small></div><div className="panel report-card"><span className="report-icon green"><ShieldCheck/></span><h3>Data caveats</h3><p>Reports distinguish observed fields from unsupported assumptions.</p><small>Source records still require verification</small></div></div>{report&&<div className="callout-note"><ShieldCheck size={17}/><span>Report downloaded from the current workspace dataset.</span></div>}</>
}
function SettingsView({settings,onChange,notify}:{settings:WorkspaceSettings;onChange:(settings:WorkspaceSettings)=>void;notify:(s:string)=>void}){
 const update=(change:Partial<WorkspaceSettings>)=>onChange({...settings,...change})
 return <div className="settings-layout"><div className="settings-menu panel"><button className="selected">General workspace</button><button onClick={()=>notify('Profile settings require authentication and are not needed for this local workspace.')}>Profile</button><button onClick={()=>notify('Browser notifications are not enabled in local mode.')}>Notifications</button><button onClick={()=>notify('API configuration belongs on the backend, never in the browser.')}>API & integrations</button></div><div className="panel settings-content"><h3>Workspace preferences</h3><p>These preferences are saved in this browser at no cost.</p><label className="setting-row"><span><b>Default market</b><small>Geographic scope for product exploration</small></span><select aria-label="Default market" className="select" value={settings.defaultMarket} onChange={event=>update({defaultMarket:event.target.value as WorkspaceSettings['defaultMarket']})}><option>Nigeria</option><option>Lagos State</option><option>Abuja FCT</option></select></label><label className="setting-row"><span><b>Default currency</b><small>Display currency for asking prices</small></span><select aria-label="Default currency" className="select" value={settings.currency}><option>NGN — Nigerian Naira</option></select></label><label className="setting-row"><span><b>Compact layout</b><small>Reduce spacing when working with larger datasets</small></span><button aria-pressed={settings.compactMode} className={`toggle ${settings.compactMode?'on':''}`} onClick={()=>update({compactMode:!settings.compactMode})}/></label><label className="setting-row"><span><b>Weekly market digest</b><small>Saved as a preference; delivery needs an account later</small></span><button aria-pressed={settings.weeklyDigest} className={`toggle ${settings.weeklyDigest?'on':''}`} onClick={()=>update({weeklyDigest:!settings.weeklyDigest})}/></label><div className="settings-actions"><button className="btn btn-primary" onClick={()=>notify('Preferences saved in this browser.')}>Save preferences</button></div></div></div>
}
export default App
