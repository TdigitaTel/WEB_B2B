"use client";
import OperatorAccess from "./OperatorAccess";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import HomeOrders from "./HomeOrders";
import CustomerAccess, {InitialPassword} from "./CustomerAccess";
import {QrLogin} from "./QrAccess";
import QuantityInput from "./QuantityInput";
import OperatorDeliveryNote from "./OperatorDeliveryNote";
import OrderDeliveryNotes, {type DeliveryNoteHeader} from "./OrderDeliveryNotes";
import OrderDeliveryDeadline from "./OrderDeliveryDeadline";
import DeleteOrderDialog from "./DeleteOrderDialog";
import CategoryUpload from "./CategoryUpload";
import CategoryVisibility from "./CategoryVisibility";
import Subusers, {AccountQr} from "./Subusers";
import SearchParameters from "./SearchParameters";
import OrderLinePlanning, {LinePlanningParameters} from "./OrderLinePlanning";
import {LinePlanningProvider,LinePlanningInfo} from "./LinePlanningInfo";
import BrandParameters from "./BrandParameters";
import SalesOrderSeries from "./SalesOrderSeries";
import CatalogPrice, {highlightedPrice} from "./CatalogPrice";
import ProductTypeSynonyms from "./ProductTypeSynonyms";
import LoginAppearanceSettings, {useLoginAppearance} from "./LoginAppearance";
import "./settings.css";
import Replenishment from "./Replenishment";

type View = "operator-access" | "replenishment" | "pickup-settings" | "home" | "catalog" | "orders" | "documents" | "ops" | "category-upload" | "category-visibility" | "customer-access" | "account";
type User = { operator_permissions?:Record<string,boolean>; access_code?:string; contact_phone?:string; can_view_prices?:boolean; can_view_delivery_notes?:boolean; can_view_invoices?:boolean; can_manage_preferences?:boolean; own_orders_only?:boolean; is_subuser?:boolean; can_manage_subusers?:boolean; login_name?:string; principal_user_name?:string; id: string; name: string; email: string; role: string; idle_timeout_seconds: number; must_change_password: boolean; show_delivery_note_images?:boolean; show_order_images?:boolean };
const operatorViewModules:Record<string,string>={ops:'orders',replenishment:'replenishment','pickup-settings':'settings','customer-access':'customers','category-upload':'categories','category-visibility':'categories','operator-access':'users'};
function operatorViewAllowed(user:User,view:string){return !operatorViewModules[view]||user.operator_permissions?.[operatorViewModules[view]]!==false}
function operatorStart(user:User):View{return (Object.keys(operatorViewModules).find(view=>operatorViewAllowed(user,view))||'account') as View}

type AccountCustomer = { trade_name: string; legal_name: string; erp_id: string; tax_id: string; email: string; phone: string; billing_address: string; price_list: string; discount_pct: number };
type Store = { id: string; code: string; name: string; address: string; company_code: number; warehouse_code: string; warehouse_name: string };
type Stock = { store_code: string; store: string; available: number };
type Suggestion = { price_includes_tax?:boolean; id: string; sku: string; name: string; price: number|null; area_id: number; family_id: number; subfamily_id: number; product_type_id: number };
type Product = { highlight_price_without_tax?:boolean; id: string; image_url: string; sku: string; name: string; brand: string; family: string; customer_price: number|null; list_price: number|null; price_with_tax: number|null; price_without_tax: number|null; tax_rate: number|null; total_available: number; stock: Stock[]; purchased_units?: number };
type CartItem = { id: number; product_id: string; sku: string; name: string; quantity: number; unit_price: number|null; line_total: number };
type OrderLine = { line_key?:string; discount_pct?:number|null; net_amount?:number|null; sku: string; description: string; quantity: number; served_quantity?: number|null; pending_quantity?: number|null; unit: string; unit_price: number|null; line_total: number|null; fulfillment_zone?: string };
type Cart = { delivery_enabled?:boolean; items: CartItem[]; line_count: number; subtotal: number|null; tax_total: number|null; total: number|null; store: { id: string; name: string } | null };
type OrderDocument = { id: string; type: "ALBARAN"|"FACTURA"; number: string; total: number|null; created_at: string; status?: string; available: boolean };
type OrderHistoryEvent = { estado_registro_exit: string; source: string; note?: string|null; date_only?:boolean; created_at: string };
type WorkflowStep = { date_only?:boolean; etapa: "BORRADOR"|"PENDIENTE"|"EN_PROCESAMIENTO"|"PENDIENTE_RECOJO"|"ENTREGADO"|"FACTURADO"; completed_at: string|null };
type StockShortage = { sku:string; name:string; requested:number; available:number };
type Order = { delivery_notes?:DeliveryNoteHeader[]|null; fulfillment_method?:"PICKUP"|"DELIVERY"; delivery_address?:string|null; attended_at?:string|null; server_now?:string; attention_deadline_at?:string|null; preparation_minutes_snapshot?:number|null; pickup_date?:string|null; delivery_order_id?:string|null; delivered_at?:string|null; operational_workflow?:{stage:string;occurred_at:string|null}[]; kardex_started_at?:string|null; kardex_closed_at?:string|null; kardex_date_error?:boolean; closed_at?:string|null; dispatch_seconds?:number|null; dispatch_date_error?:boolean; id: string; number: string; web_number?:string|null; exit_number?:string|null; local_order?:boolean; customer_code?: string|null; nro_pedido_exit?: string|null; fecha_registro_exit?: string|null; origen_pedido?: "B2B"|"EXIT"; estado_registro_exit?: string|null; workflow?: WorkflowStep[]; history_enabled?: boolean; history?: OrderHistoryEvent[]; stock_warning?:{store:string;items:StockShortage[]}|null; auxiliary_reference?:string|null; is_web_order?:boolean; store: string; customer: string; created_by: string; creator_user_name?:string; principal_user_name?:string; customer_reference?: string; job_name?: string; notes?: string; subtotal: number|null; tax_total: number|null; total: number|null; created_at: string; items?: OrderLine[]; documents?: OrderDocument[] };
type DocumentItem = { line:number; sku:string; description:string; unit:string; quantity:number; unit_price:number|null; discount_pct:number|null; net_amount:number|null; tax_rate:number|null; tax_amount:number|null; total:number|null; warehouse:string; dispatch_delegation?:string };
type DocumentRow = { id: string; number: string; total: number|null; subtotal?: number|null; tax_total?: number|null; created_at?: string; due_date?: string; status?: string; store_code?: string; store_name?: string; order_number?: string; invoice_number?: string; document?: string; source?: string; items?:DocumentItem[] };
type ProductTypeNode = { id: number; code: string; name: string; count: number };
type SubfamilyNode = { id: number; code: string; name: string; count: number; product_types: ProductTypeNode[] };
type FamilyNode = { id: number; code: string; name: string; count: number; subfamilies: SubfamilyNode[] };
type AreaNode = { id: number; code: string; name: string; image_url?: string|null; count: number; families: FamilyNode[] };
type CatalogFilters = { areaId: string; familyId: string; subfamilyId: string; productTypeId: string };
type OperationsView = "active_kardex" | "attended" | "active_sga" | "web";

const emptyCatalogFilters: CatalogFilters = { areaId: "", familyId: "", subfamilyId: "", productTypeId: "" };

function productsUrl(text: string, filters: CatalogFilters, page = 1) {
  const params = new URLSearchParams({ q: text, page: String(page), page_size: "48" });
  if (filters.areaId) params.set("area_id", filters.areaId);
  if (filters.familyId) params.set("family_id", filters.familyId);
  if (filters.subfamilyId) params.set("subfamily_id", filters.subfamilyId);
  if (filters.productTypeId) params.set("product_type_id", filters.productTypeId);
  return `/api/v1/products?${params.toString()}`;
}

async function api<T>(url: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...options, credentials: "include", headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  if(response.status===401 && url!=="/api/v1/auth/login") window.dispatchEvent(new Event("session-expired"));
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; }
  catch { throw new Error("El servicio no está disponible. Inténtalo de nuevo en unos segundos."); }
  if (!response.ok) throw new Error(data.detail || "No se pudo completar la operación");
  return data as T;
}

const money = (value: number|null|undefined) => value == null ? "••••" : value.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
const deadlineLabel = (value:string) => new Date(value).toLocaleString("es-ES",{timeZone:"Europe/Madrid",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"});
const units = (value: number) => value.toLocaleString("es-ES", { maximumFractionDigits: 3 });
const orderStateLabel = (value: string) => ({
  PENDIENTE_RECOJO: "PENDIENTE DE RECOJO",
  EN_PROCESAMIENTO: "EN PROCESAMIENTO",
}[value] || value.replaceAll("_", " "));
const deliveryNoteStateLabel = (state:string|undefined) => {
  const labels:Record<string,string> = {EMITIDO:"Emitido",ENTREGADO:"Emitido",IMPRESO:"Emitido",PENDIENTE_EMISION:"Pendiente de emisión",PENDIENTE_DE_ENTREGA:"Pendiente de emisión",FACTURADO:"Facturado"};
  return labels[state||""] || orderStateLabel(state||"REGISTRADO");
};
const visibleOrderStage = (estado?: string|null) => ({
  BORRADOR: "BORRADOR",
  PENDIENTE: "PENDIENTE",
  BLOQUEADO: "EN_PROCESAMIENTO",
  REGISTRADO: "EN_PROCESAMIENTO",
  EN_PROCESO: "EN_PROCESAMIENTO",
  EN_PREPARACION: "EN_PROCESAMIENTO",
  ATENDIDO: "PENDIENTE_RECOJO",
  ENTREGADO: "ENTREGADO",
  FACTURADO: "FACTURADO",
}[String(estado||"PENDIENTE").toUpperCase()] || "PENDIENTE");
const madridDate = (value: Date | string) => new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Madrid", year: "numeric", month: "2-digit", day: "2-digit"
}).format(new Date(value));

export default function Page() {
  const [user, setUser] = useState<User | null>(null);
  const [customer, setCustomer] = useState<AccountCustomer | null>(null);
  const [view, setView] = useState<View>("home");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestionsEnabled, setSuggestionsEnabled] = useState(true);
  const [products, setProducts] = useState<Product[]>([]);
  const [favoriteProducts, setFavoriteProducts] = useState<Product[]>([]);
  const [totalProducts, setTotalProducts] = useState(0);
  const [catalogPage, setCatalogPage] = useState(1);
  const [loadingMoreProducts, setLoadingMoreProducts] = useState(false);
  const [classification, setClassification] = useState<AreaNode[]>([]);
  const [catalogFilters, setCatalogFilters] = useState<CatalogFilters>(emptyCatalogFilters);
  const [stores, setStores] = useState<Store[]>([]);
  const [cart, setCart] = useState<Cart | null>(null);
  const cartUpdates=useRef<Promise<void>>(Promise.resolve());
  const [cartOpen, setCartOpen] = useState(false);
  const [selectedDeliveryNote,setSelectedDeliveryNote]=useState("");
  const [orders, setOrders] = useState<Order[]>([]);
  const [refreshingOrders, setRefreshingOrders] = useState(false);
  const [deliveryNotes, setDeliveryNotes] = useState<DocumentRow[]>([]);
  const [invoices, setInvoices] = useState<DocumentRow[]>([]);
  const [opsOrders, setOpsOrders] = useState<Order[]>([]);
  const opsRequest = useRef(0);
  const opsRequestView = useRef<OperationsView|null>(null);
  const [kioskMode, setKioskMode] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [orderConfirmation, setOrderConfirmation] = useState<Order | null>(null);
  const [deleteCandidate,setDeleteCandidate]=useState<Order|null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [catalogMenuOpen,setCatalogMenuOpen]=useState(false);

  const isOperator = user?.role === "OPERADOR_TIENDA" || user?.role === "ADMIN";

  const loadAccount = useCallback(async () => {
    try {
      const account = await api<{ user: User; customer: typeof customer }>("/api/v1/account");
      setUser(account.user); setCustomer(account.customer);
      if (account.user.role === "OPERADOR_TIENDA" || account.user.role === "ADMIN") setView(operatorStart(account.user));
    } catch { setUser(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadAccount(); }, [loadAccount]);

  useEffect(() => {
    const expire = () => { setUser(null); setCustomer(null); setProducts([]); setFavoriteProducts([]); setOrders([]); setOpsOrders([]); setCart(null); setDeliveryNotes([]); setInvoices([]); setCartOpen(false); setMenuOpen(false); setCatalogMenuOpen(false); setView("home"); setError("La sesión ha finalizado. Inicia sesión de nuevo."); };
    const hide = () => { document.documentElement.style.visibility="hidden"; };
    const restore = (event: PageTransitionEvent) => {
      if(event.persisted){ location.reload(); return; }
      document.documentElement.style.visibility="";
    };
    window.addEventListener("session-expired",expire);
    window.addEventListener("pagehide",hide);
    window.addEventListener("pageshow",restore);
    return () => { window.removeEventListener("session-expired",expire); window.removeEventListener("pagehide",hide); window.removeEventListener("pageshow",restore); };
  }, []);

  useEffect(() => {
    if(!user) return;
    const idleTimeout=user.idle_timeout_seconds*1000;
    let lastActivity=Date.now(), lastSent=Date.now(), pending=0;
    const expire = () => { window.dispatchEvent(new Event("session-expired")); void fetch("/api/v1/auth/logout",{method:"POST",credentials:"include"}); };
    const sendActivity = () => { lastSent=Date.now(); void api("/api/v1/auth/activity",{method:"POST"}).catch(()=>{}); };
    const activity = (event: Event) => {
      if(!event.isTrusted) return;
      if(Date.now()-lastActivity>=idleTimeout){expire();return;}
      lastActivity=Date.now(); window.clearTimeout(pending);
      if(lastActivity-lastSent>=1000) sendActivity();
      pending=window.setTimeout(sendActivity,1000);
    };
    const check = () => { if(Date.now()-lastActivity>=idleTimeout) expire(); };
    const events=["pointerdown","pointermove","keydown","scroll","touchstart"];
    events.forEach(name=>window.addEventListener(name,activity,{passive:true}));
    const timer=window.setInterval(check,1000);
    const validation=window.setInterval(()=>{ void api("/api/v1/account").catch(()=>{}); },15000);
    document.addEventListener("visibilitychange",check);
    return () => { events.forEach(name=>window.removeEventListener(name,activity)); window.clearTimeout(pending); window.clearInterval(timer); window.clearInterval(validation); document.removeEventListener("visibilitychange",check); };
  }, [user]);

  useEffect(() => {
    const forced = new URLSearchParams(window.location.search).get("kiosk") === "1";
    const touchKiosk = window.matchMedia("(pointer: coarse)").matches && window.innerWidth >= 800;
    setKioskMode(forced || touchKiosk);
  }, []);

  const refreshCustomerData = useCallback(async () => {
    if (!user || user.must_change_password || isOperator) return;
    const [storeData, cartData, classificationData, favoriteData] = await Promise.all([
      api<Store[]>("/api/v1/stores"), api<Cart>("/api/v1/cart"),
      api<AreaNode[]>("/api/v1/catalog/classification"),
      api<{items:Product[];total:number}>("/api/v1/catalog/favorites?limit=8")
    ]);
    setStores(storeData); setCart(cartData); setClassification(classificationData); setFavoriteProducts(favoriteData.items);
  }, [user, isOperator]);

  const lastOrdersQuery = useRef({from:madridDate(new Date()),to:madridDate(new Date()),state:"PENDIENTE"});
  const refreshOrders = useCallback(async (from = madridDate(new Date()), to = madridDate(new Date()), state = "TODOS") => {
    if (!user || user.must_change_password || isOperator) return;
    lastOrdersQuery.current={from,to,state};
    setRefreshingOrders(true);
    try { const params=new URLSearchParams({date_from:from,date_to:to,state});setOrders(await api<Order[]>(`/api/v1/orders?${params}`)); setError(""); }
    catch (e) { setError((e as Error).message); }
    finally { setRefreshingOrders(false); }
  }, [user, isOperator]);

  const refreshOperations = useCallback(async (mode: OperationsView = "active_kardex", from = "", to = "", state = "TODOS", delegation = "TODAS") => {
    const request = ++opsRequest.current;
    if(opsRequestView.current!==mode){setOpsOrders([]);opsRequestView.current=mode;}
    const params = new URLSearchParams({ view: mode });
    if ((mode === "attended"||mode === "web") && from) params.set("date_from", from);
    if ((mode === "attended"||mode === "web") && to) params.set("date_to", to);
    if (mode === "web") {params.set("state",state);params.set("delegation",delegation);}
    try {
      const records=await api<Order[]>(`/api/v1/store/orders?${params}`);
      if(request!==opsRequest.current)return;
      setOpsOrders(mode==="web"?records.filter(order=>order.origen_pedido==="B2B"):records);
      setError("");
    } catch(e) {
      if(request!==opsRequest.current)return;
      setOpsOrders([]);
      throw e;
    }
  }, []);

  useEffect(() => { refreshCustomerData().catch(e => setError(e.message)); }, [refreshCustomerData]);

  useEffect(() => {
    if (view !== "orders" || !user || user.must_change_password || isOperator) return;
    refreshOrders();
  }, [view, user, isOperator, refreshOrders]);

  const selectCatalogCategory = useCallback((filters:CatalogFilters)=>{
    setQuery("");
    setSuggestionsEnabled(false);
    setSuggestions([]);
    setCatalogPage(1);
    setCatalogFilters(filters);
    setView("catalog");
  },[]);

  const searchProducts = useCallback(async (text = query, filters = catalogFilters) => {
    if (!user || user.must_change_password || isOperator) return;
    const result = await api<{ items: Product[]; total: number }>(productsUrl(text, filters));
    setProducts(result.items); setTotalProducts(result.total); setCatalogPage(1);
  }, [query, catalogFilters, user, isOperator]);

  useEffect(() => {
    if (!user || user.must_change_password || isOperator) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const result = await api<{items:Product[];total:number}>(productsUrl(query, catalogFilters), {signal:controller.signal});
        setProducts(result.items); setTotalProducts(result.total); setCatalogPage(1); setLoadingMoreProducts(false); setError("");
      } catch(e) { if (!controller.signal.aborted) setError((e as Error).message); }
    }, 220);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, catalogFilters, user, isOperator]);

  const loadMoreProducts = useCallback(async () => {
    if (!user || user.must_change_password || isOperator || loadingMoreProducts || products.length >= totalProducts) return;
    const nextPage = catalogPage + 1;
    setLoadingMoreProducts(true);
    try {
      const result = await api<{items:Product[];total:number}>(productsUrl(query, catalogFilters, nextPage));
      setProducts(current => {
        const known = new Set(current.map(product => product.id));
        return [...current, ...result.items.filter(product => !known.has(product.id))];
      });
      setTotalProducts(result.total); setCatalogPage(nextPage);
    } catch (e) { setError((e as Error).message); }
    finally { setLoadingMoreProducts(false); }
  }, [user, isOperator, loadingMoreProducts, products.length, totalProducts, catalogPage, query, catalogFilters]);

  useEffect(() => {
    if (!user || user.must_change_password || !suggestionsEnabled || query.trim().length < 2 || isOperator) { setSuggestions([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => api<Suggestion[]>(`/api/v1/search/suggestions?q=${encodeURIComponent(query)}`).then(items => { if (!cancelled) setSuggestions(items); }).catch(() => { if (!cancelled) setSuggestions([]); }), 180);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, user, isOperator, suggestionsEnabled]);

  useEffect(() => {
    if (view === "documents" && user && !user.must_change_password && !isOperator) Promise.all([user.can_view_delivery_notes!==false?api<DocumentRow[]>("/api/v1/delivery-notes"):Promise.resolve([]), user.can_view_invoices!==false?api<DocumentRow[]>("/api/v1/invoices"):Promise.resolve([])]).then(([a, b]) => { setDeliveryNotes(a); setInvoices(b); });
    if (view === "ops" && isOperator) refreshOperations().catch(e => setError(e.message));
  }, [view, user, isOperator, refreshOperations]);

  async function login(email: string, password: string) {
    setError("");
    const result = await api<{ user: User }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setUser(result.user); setLoading(true); await loadAccount();
  }

  async function loginQr(token:string){
    setError("");
    const result=await api<{user:User}>("/api/v1/auth/qr",{method:"POST",body:JSON.stringify({token})});
    setUser(result.user);setLoading(true);await loadAccount();
  }

  async function logout() { try { await api("/api/v1/auth/logout", { method: "POST" }); } finally { window.dispatchEvent(new Event("session-expired")); location.replace(location.pathname); } }

  async function addProduct(productId: string, quantity = 1) {
    await cartUpdates.current;
    const updated = await api<Cart>("/api/v1/cart/items", { method: "POST", body: JSON.stringify({ product_id: productId, quantity }) });
    setCart(updated); setSuggestions([]);
  }

  function queueCartUpdate(update:()=>Promise<Cart>){
    const request=cartUpdates.current.catch(()=>{}).then(async()=>{setCart(await update())});
    cartUpdates.current=request;
    void request.catch(error=>setError((error as Error).message));
    return request;
  }

  function updateCart(itemId: number, quantity: number) {
    if(!Number.isFinite(quantity)||quantity<1||quantity>99999)return;
    return queueCartUpdate(()=>api<Cart>(`/api/v1/cart/items/${itemId}`, { method: "PATCH", body: JSON.stringify({ quantity }) }));
  }

  function removeCart(itemId: number) { return queueCartUpdate(()=>api<Cart>(`/api/v1/cart/items/${itemId}`, { method: "DELETE" })); }

  async function repeatOrder(id: string) { setCart(await api<Cart>(`/api/v1/orders/${id}/repeat`, { method: "POST" })); setCartOpen(true); }

  async function checkout(storeId: string, jobName: string, reference: string, notes: string, draft: boolean, pickupDate: string, fulfillmentMethod: string, deliveryAddress: string) {
    await cartUpdates.current;
    const selectedStore=stores.find(store=>store.id===storeId);
    if(!selectedStore)throw new Error("Selecciona una delegación válida");
    const order = await api<Order>("/api/v1/orders", { method: "POST", body: JSON.stringify({ company_code: selectedStore.company_code, delegation_code: selectedStore.code, job_name: jobName || null, customer_reference: reference || null, notes: notes || null, draft, fulfillment_method: fulfillmentMethod, delivery_address: deliveryAddress || null, pickup_date: pickupDate || null }) });
    setCartOpen(false); setView("orders"); setOrderConfirmation(order); await Promise.all([refreshCustomerData(),refreshOrders()]);
  }

  async function submitDraft(id: string) {
    try {
      await api<Order>(`/api/v1/orders/${id}/submit`, { method: "POST" });
      setError(""); await Promise.all([refreshCustomerData(),refreshOrders()]);
    } catch (e) { setError((e as Error).message); }
  }

  async function deleteOrder(id: string) {
    await api(`/api/v1/orders/${id}`, { method: "DELETE" });
    setOrders(current=>current.filter(order=>order.id!==id));
    setDeleteCandidate(null);setError("");
    const {from,to,state}=lastOrdersQuery.current;
    void refreshOrders(from,to,state).catch(e=>setError((e as Error).message));
  }

  if (loading) return <div className="loading">Preparando el portal profesional…</div>;
  if (!user) return <Login onLogin={login} onQrLogin={loginQr} error={error} />;

  if (user.must_change_password) return <InitialPassword onChanged={loadAccount} onLogout={logout}/>;

  return <main className={`shell ${isOperator?"operator-shell":""} ${kioskMode?"kiosk-mode":""} ${keyboardOpen?"keyboard-open":""}`}>
    <header className="header">
      <div className="head">
        <button className="brand" onClick={() => setView(isOperator ? operatorStart(user) : "home")} aria-label="Inicio"><img src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa · 25 aniversario" /></button>
        {!isOperator&&<button className="menu-button" onClick={()=>setMenuOpen(true)}><span aria-hidden="true">☰</span> Menú</button>}
        {!isOperator && <div className="global-search">
          <form className="search-form" onSubmit={e => { e.preventDefault(); setView("catalog"); setSuggestionsEnabled(false); setSuggestions([]); searchProducts().catch(e=>setError(e.message)); }}>
            <select aria-label="Departamento" value={catalogFilters.areaId} onChange={e=>selectCatalogCategory({areaId:e.target.value,familyId:"",subfamilyId:"",productTypeId:""})}><option value="">Todos los departamentos</option>{classification.map(area=><option key={area.id} value={area.id}>{area.name}</option>)}</select>
            <input aria-label="Buscar productos" value={query} onChange={e => {setQuery(e.target.value);setSuggestionsEnabled(true);setCatalogFilters(emptyCatalogFilters);setView("catalog")}} onKeyDown={e=>{if(e.key==="Escape"){setSuggestionsEnabled(false);setSuggestions([])}}} placeholder="Busca por producto, referencia o medida" />
            {!!query && <button className="search-clear" aria-label="Limpiar búsqueda" type="button" onClick={()=>{setQuery("");setCatalogFilters(emptyCatalogFilters);setSuggestionsEnabled(false);setSuggestions([]);setView("catalog")}}>×</button>}
            {kioskMode&&<button className="keyboard-toggle" aria-label="Abrir teclado en pantalla" type="button" onClick={()=>setKeyboardOpen(value=>!value)}>⌨</button>}
            <button className="search-submit" aria-label="Buscar" type="submit">⌕</button>
          </form>
          {!!suggestions.length && <div className="suggestions" role="listbox" aria-label="Sugerencias de productos">{suggestions.map(p => <button className="suggestion" role="option" key={p.id} onClick={() => {setSuggestionsEnabled(false);setQuery(p.name);setCatalogFilters({areaId:String(p.area_id),familyId:String(p.family_id),subfamilyId:String(p.subfamily_id),productTypeId:String(p.product_type_id)});setSuggestions([]);setView("catalog")}}><span><b>{p.name}</b><br/><small>Código {p.sku}</small></span><span className="suggestion-side"><b>{money(p.price)}</b><small>{p.price_includes_tax===false?"Sin IVA":"Con IVA"} · Ver producto →</small></span></button>)}</div>}
        </div>}
        <button className="account-button" onClick={()=>setView("account")}><small>Hola, {user.name.split(" ")[0]}</small><b>Mi cuenta</b></button><button className="logout-button" onClick={logout}>Salir</button>
        {!isOperator && <button className="cart-button" onClick={() => setCartOpen(true)}>▤ <span>Mi carrito</span> {cart?.line_count || 0}</button>}
      </div>
      <nav className="desktop-nav">{(isOperator ? [["ops","Operaciones"],["replenishment","Reposición"],["pickup-settings","Parámetros"],["customer-access","Accesos de clientes"],["category-upload","Carga de categorías"],["category-visibility","Categorías e imágenes"],["operator-access","Accesos de usuarios"],["account","Mi cuenta"]] : [["home","Inicio"],["catalog","Catálogo"],["orders","Mis pedidos"],["documents","Albaranes y facturas"],["account","Mi cuenta"]]).filter(([id])=>(!isOperator||operatorViewAllowed(user,id))&&(id!=="documents"||user.can_view_delivery_notes!==false||user.can_view_invoices!==false)).map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>
    </header>
    <div className="service-strip"><span>ÁREA PROFESIONAL · Compra a tu ritmo</span><span>Almeiras · Recogida en tienda</span></div>{error && <div className="page error" role="alert">{error}</div>}
    {view === "home" && <Home key={user.id} customer={customer} products={favoriteProducts} classification={classification} onNavigate={setView} onSelectArea={areaId=>selectCatalogCategory({areaId:String(areaId),familyId:"",subfamilyId:"",productTypeId:""})} onAdd={addProduct} />}
    {view === "catalog" && <Catalog products={products} total={totalProducts} classification={classification} filters={catalogFilters} setFilters={selectCatalogCategory} onAdd={addProduct} onLoadMore={loadMoreProducts} loadingMore={loadingMoreProducts} />}
    {view === "orders" && <Orders canViewNotes={user.can_view_delivery_notes!==false} onOpenNote={number=>{setSelectedDeliveryNote(number);setView("documents")}} showImages={!!user.show_order_images} orders={orders} refreshing={refreshingOrders} onRefresh={refreshOrders} onRepeat={repeatOrder} onSubmitDraft={submitDraft} onDelete={id=>{const order=orders.find(row=>row.id===id);if(order)setDeleteCandidate(order)}} />}
    {view === "documents" && <Documents initialNote={selectedDeliveryNote} canViewNotes={user.can_view_delivery_notes!==false} canViewInvoices={user.can_view_invoices!==false} canViewPrices={user.can_view_prices!==false} showImages={!!user.show_delivery_note_images} notes={deliveryNotes} invoices={invoices} />}
    {view === "account" && (isOperator?<div className="page account-page"><h1>Mi cuenta</h1><PasswordSettings/></div>:<Account user={user} customer={customer} onPreferences={preferences=>setUser(previous=>previous?{...previous,...preferences}:previous)} />)}

    {view === "replenishment" && isOperator && operatorViewAllowed(user,"replenishment") && <Replenishment />}
    {view === "ops" && isOperator && operatorViewAllowed(user,"ops") && <Operations orders={opsOrders} onRefresh={refreshOperations} />}
    {view === "pickup-settings" && isOperator && operatorViewAllowed(user,"pickup-settings") && <PickupParameters />}
    {view === "operator-access" && isOperator && operatorViewAllowed(user,"operator-access") && <OperatorAccess />}
    {view === "customer-access" && isOperator && operatorViewAllowed(user,"customer-access") && <CustomerAccess />}
    {view === "category-upload" && isOperator && operatorViewAllowed(user,"category-upload") && <CategoryUpload />}
    {view === "category-visibility" && isOperator && operatorViewAllowed(user,"category-visibility") && <CategoryVisibility />}
    {isOperator&&<nav className="mobile-nav" aria-label="Navegación de operador">{[["ops","Pedidos"],["replenishment","Reposición"],["pickup-settings","Parámetros"],["customer-access","Clientes"],["operator-access","Usuarios"],["account","Cuenta"]].filter(([id])=>operatorViewAllowed(user,id)).map(([id,label])=><button key={id} className={view===id?"active":""} onClick={()=>setView(id as View)}>{label}</button>)}</nav>}
    {!isOperator && <nav className="mobile-nav">{[["home","Inicio"],["catalog","Buscar"],["orders","Pedidos"],["account","Cuenta"]].map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>}
    {cartOpen && cart && <CartDrawer cart={cart} stores={stores} onClose={() => setCartOpen(false)} onContinue={()=>{setCartOpen(false);setView("catalog")}} onUpdate={updateCart} onRemove={removeCart} onCheckout={checkout} />}
    {deleteCandidate&&<DeleteOrderDialog order={deleteCandidate} onCancel={()=>setDeleteCandidate(null)} onConfirm={()=>deleteOrder(deleteCandidate.id)}/>}
    {orderConfirmation && <OrderConfirmation order={orderConfirmation} onClose={()=>setOrderConfirmation(null)} onViewOrders={()=>{setOrderConfirmation(null);setView("orders")}} />}
    {menuOpen&&!isOperator&&<SiteMenu onClose={()=>setMenuOpen(false)} onNavigate={next=>{setView(next);setMenuOpen(false)}} onCatalog={()=>{setMenuOpen(false);setCatalogMenuOpen(true);setView("catalog")}}/>}
    {catalogMenuOpen&&!isOperator&&<CatalogMenu classification={classification} onClose={()=>setCatalogMenuOpen(false)} onSelect={filters=>{selectCatalogCategory(filters);setCatalogMenuOpen(false)}} />}
    {kioskMode&&keyboardOpen&&<KioskKeyboard onKey={key=>{if(key==="BACKSPACE")setQuery(value=>Array.from(value).slice(0,-1).join(""));else if(key==="CLEAR")setQuery("");else if(key==="SPACE")setQuery(value=>value+" ");else setQuery(value=>value+key);setSuggestionsEnabled(true);setCatalogFilters(emptyCatalogFilters);setView("catalog")}} onSearch={()=>{setKeyboardOpen(false);setSuggestionsEnabled(false);setSuggestions([]);searchProducts().catch(e=>setError(e.message))}} onClose={()=>setKeyboardOpen(false)}/>}
  </main>;
}

function KioskKeyboard({onKey,onSearch,onClose}:{onKey:(key:string)=>void;onSearch:()=>void;onClose:()=>void}) { const rows=[["1","2","3","4","5","6","7","8","9","0","/",'"'],["Q","W","E","R","T","Y","U","I","O","P"],["A","S","D","F","G","H","J","K","L","Ñ"],["Z","X","C","V","B","N","M","-","."]]; return <aside className="kiosk-keyboard" aria-label="Teclado en pantalla"><div className="keyboard-head"><b>Teclado en pantalla</b><button onClick={onClose} aria-label="Cerrar teclado">×</button></div>{rows.map((row,index)=><div className="keyboard-row" key={index}>{row.map(key=><button key={key} onClick={()=>onKey(key)}>{key}</button>)}</div>)}<div className="keyboard-row keyboard-actions"><button onClick={()=>onKey("CLEAR")}>Limpiar</button><button className="space-key" onClick={()=>onKey("SPACE")}>Espacio</button><button onClick={()=>onKey("BACKSPACE")}>⌫ Borrar</button><button className="keyboard-search" onClick={onSearch}>Buscar</button></div></aside> }

function SiteMenu({onClose,onNavigate,onCatalog}:{onClose:()=>void;onNavigate:(view:View)=>void;onCatalog:()=>void}) {
  return <div className="menu-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="site-menu" role="dialog" aria-modal="true" aria-label="Menú de navegación"><header><h2>Menú</h2><button aria-label="Cerrar menú" onClick={onClose}>×</button></header><nav aria-label="Secciones de la web"><button onClick={()=>onNavigate("home")}>Inicio</button><details><summary>Catálogo profesional</summary><div><button onClick={()=>onNavigate("catalog")}>Ver catálogo</button><button onClick={onCatalog}>Explorar familias y subfamilias ›</button></div></details><button onClick={()=>onNavigate("orders")}>Mis pedidos</button><button onClick={()=>onNavigate("documents")}>Albaranes y facturas</button><button onClick={()=>onNavigate("account")}>Mi cuenta</button><a className="manual-menu-link" href="/manual-guia-tareas.pdf?v=20261011-6" target="_blank" rel="noopener noreferrer">Manual de uso por tareas ↗</a><a className="manual-menu-link" href="/manual-guia-tareas.pdf?v=20261011-6" download>Descargar manual PDF ↓</a></nav></section></div>
}

function CatalogMenu({classification,onClose,onSelect}:{classification:AreaNode[];onClose:()=>void;onSelect:(filters:CatalogFilters)=>void}) { const [areaId,setAreaId]=useState(String(classification[0]?.id||"")); const area=classification.find(item=>String(item.id)===areaId); return <div className="menu-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="mega-menu" role="dialog" aria-modal="true" aria-label="Categorías del catálogo"><div className="mega-menu-head"><div><span className="eyebrow">CATÁLOGO PROFESIONAL</span><h2>¿Qué material necesitas?</h2></div><button aria-label="Cerrar menú" onClick={onClose}>×</button></div><div className="mega-menu-body"><nav className="mega-departments"><b>Departamentos</b>{classification.map(item=><button key={item.id} className={areaId===String(item.id)?"active":""} onMouseEnter={()=>setAreaId(String(item.id))} onClick={()=>setAreaId(String(item.id))}>{item.name}<span>›</span></button>)}</nav><div className="mega-content"><button className="mega-all" onClick={()=>onSelect({areaId:String(area?.id||""),familyId:"",subfamilyId:"",productTypeId:""})}>Ver todo en {area?.name||"el catálogo"} →</button><div className="mega-family-grid">{area?.families.map(family=><section key={family.id}><button className="mega-family" onClick={()=>onSelect({areaId:String(area.id),familyId:String(family.id),subfamilyId:"",productTypeId:""})}>{family.name}</button>{family.subfamilies.slice(0,6).map(subfamily=><button key={subfamily.id} onClick={()=>onSelect({areaId:String(area.id),familyId:String(family.id),subfamilyId:String(subfamily.id),productTypeId:""})}>{subfamily.name}</button>)}</section>)}</div></div></div></section></div> }

function Login({onLogin,onQrLogin,error}:{onQrLogin:(token:string)=>Promise<void>;onLogin:(email:string,password:string)=>Promise<void>;error:string}) {
  const appearance=useLoginAppearance();
  const [loginError,setLoginError]=useState(""); const [email,setEmail]=useState(""); const [password,setPassword]=useState(""); const [busy,setBusy]=useState(false);
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);try{await onLogin(email,password)}catch(e){setLoginError((e as Error).message)}finally{setBusy(false)}}
  return <div className="login"><section className={`login-brand ${appearance.image_url?"has-cover":""}`}>{appearance.image_url&&<img className="login-cover" src={appearance.image_url} alt="" onError={event=>{event.currentTarget.style.display="none"}}/>}<img className="login-logo" src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa"/><h1>Material profesional.<br/>Pedido en segundos.</h1><p>Consulta tu precio, comprueba stock local y deja el pedido preparado para recoger en Almeiras.</p></section><section className="login-panel"><form className="login-form" onSubmit={submit}><h2>Acceso profesional</h2><p className="small">Entra con la cuenta de tu empresa.</p><label className="label">Usuario o email</label><input className="input" value={email} onChange={e=>setEmail(e.target.value)}/><label className="label">Contraseña</label><input className="input" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)}/>{(error||loginError)&&<p className="error">{error||loginError}</p>}<button className="primary block" disabled={busy}>{busy?"Entrando…":"Iniciar sesión"}</button><QrLogin onLogin={onQrLogin}/></form></section></div>
}

const loadHomeOrders = (signal:AbortSignal) => api<Order[]>("/api/v1/orders?state=TODOS", {signal, cache:"no-store"});

function Home({customer,products,classification,onNavigate,onSelectArea,onAdd}:{customer:AccountCustomer|null;products:Product[];classification:AreaNode[];onNavigate:(v:View)=>void;onSelectArea:(id:number)=>void;onAdd:(id:string)=>void}) {
  const [openStockId,setOpenStockId]=useState<string|null>(null);
  return <div className="page"><section className="hero"><div><span className="eyebrow">TU MOSTRADOR DIGITAL</span><h1>Todo lo que necesitas.<br/>Listo para tu próxima obra.</h1><p>Hola, {customer?.trade_name || "profesional"}. Encuentra tu material y recógelo en tienda.</p><button className="primary" onClick={()=>onNavigate("catalog")}>Explorar catálogo →</button></div><div className="hero-note"><span>01 / BUSCA</span><span>02 / AÑADE</span><span>03 / RECOGE</span><b>Menos esperas.<br/>Más tiempo en obra.</b></div></section>
  <section className="department-showcase"><div className="section-heading"><div><span className="eyebrow">COMPRA POR DEPARTAMENTO</span><h2>¿Qué necesitas para tu instalación?</h2></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver todos →</button></div><div className="department-rail">{classification.slice(0,10).map((area,index)=><button key={area.id} className={`department-card tone-${index%6}`} onClick={()=>onSelectArea(area.id)}>{area.image_url?<img className="department-image" src={area.image_url} alt="" loading="lazy"/>:<span className="department-symbol" aria-hidden="true">{area.name.slice(0,2)}</span>}<b>{area.name}</b><small>{area.count.toLocaleString("es-ES")} productos</small><em>Explorar →</em></button>)}</div></section>
  <div className="home-grid"><div><section className="shortcut-grid"><button onClick={()=>onNavigate("orders")}><span>↻</span><b>Pedidos anteriores</b><small>Consulta y duplica pedidos</small></button><button onClick={()=>onNavigate("documents")}><span>▤</span><b>Tus documentos</b><small>Facturas y albaranes a mano</small></button><button onClick={()=>onNavigate("orders")}><span>✓</span><b>Estado de pedidos</b><small>Sigue cada etapa y su fecha</small></button></section><section className="section panel"><div className="section-heading"><div><span className="eyebrow">LOS QUE MÁS UTILIZAS</span><h2>Materiales favoritos</h2><p className="small">Tus artículos más comprados, ordenados por unidades.</p></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver catálogo →</button></div><div className="products">{products.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd} stockOpen={openStockId===p.id} onStockToggle={open=>setOpenStockId(open?p.id:null)}/>)}</div>{!products.length&&<p className="small">Todavía no hay compras anteriores disponibles para mostrar.</p>}</section></div>
  <aside className="activity-panel panel"><HomeOrders load={loadHomeOrders} onNavigate={()=>onNavigate("orders")} /><div className="store-note"><b>Cerca de tu próxima obra</b><p>Almeiras · A Coruña · Sanxenxo · Ferrol · Santiago</p></div></aside></div></div>;
}

function Catalog({products,total,classification,filters,setFilters,onAdd,onLoadMore,loadingMore}:{products:Product[];total:number;classification:AreaNode[];filters:CatalogFilters;setFilters:(f:CatalogFilters)=>void;onAdd:(id:string,qty?:number)=>void;onLoadMore:()=>Promise<void>;loadingMore:boolean}) {
  const [filtersOpen,setFiltersOpen]=useState(false);
  const [openStockId,setOpenStockId]=useState<string|null>(null);
  const [sort,setSort]=useState("relevance");
  const loadMoreRef=useRef<HTMLDivElement|null>(null);
  const hasMore=products.length<total;
  useEffect(()=>{const target=loadMoreRef.current;if(!target||!hasMore)return;const observer=new IntersectionObserver(entries=>{if(entries[0]?.isIntersecting&&!loadingMore)onLoadMore().catch(()=>{})},{rootMargin:"600px 0px"});observer.observe(target);return()=>observer.disconnect()},[hasMore,loadingMore,onLoadMore]);
  const selectArea=(id:number|string)=>setFilters({areaId:String(id),familyId:"",subfamilyId:"",productTypeId:""});
  const selectFamily=(areaId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(id),subfamilyId:"",productTypeId:""});
  const selectSubfamily=(areaId:number,familyId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(familyId),subfamilyId:String(id),productTypeId:""});
  const selectType=(areaId:number,familyId:number,subfamilyId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(familyId),subfamilyId:String(subfamilyId),productTypeId:String(id)});
  const area=classification.find(x=>String(x.id)===filters.areaId); const family=area?.families.find(x=>String(x.id)===filters.familyId); const subfamily=family?.subfamilies.find(x=>String(x.id)===filters.subfamilyId); const type=subfamily?.product_types.find(x=>String(x.id)===filters.productTypeId);
  const sorted=[...products].sort((a,b)=>sort==="price-asc"?(highlightedPrice(a)??0)-(highlightedPrice(b)??0):sort==="price-desc"?(highlightedPrice(b)??0)-(highlightedPrice(a)??0):sort==="name"?a.name.localeCompare(b.name,"es"):0);
  const hasFilters=!!(filters.areaId||filters.familyId||filters.subfamilyId||filters.productTypeId);
  return <div className="page catalog-page"><div className="catalog-title"><div><span className="eyebrow">CATÁLOGO PROFESIONAL</span><h1>{type?.name||subfamily?.name||family?.name||area?.name||"Productos para tu instalación"}</h1><p>Encuentra material por departamento y afina el resultado con filtros.</p></div></div>{hasFilters&&<nav className="catalog-breadcrumb" aria-label="Ruta de categoría"><button onClick={()=>setFilters(emptyCatalogFilters)}>Catálogo</button><span>›</span>{area&&<><button onClick={()=>selectArea(area.id)}>{area.name}</button></>}{family&&<><span>›</span><button onClick={()=>selectFamily(area!.id,family.id)}>{family.name}</button></>}{subfamily&&<><span>›</span><button onClick={()=>selectSubfamily(area!.id,family!.id,subfamily.id)}>{subfamily.name}</button></>}{type&&<><span>›</span><b>{type.name}</b></>}</nav>}{hasFilters&&<div className="active-filter-bar"><span>Filtros aplicados</span>{area&&<button onClick={()=>setFilters(emptyCatalogFilters)}>{area.name} ×</button>}{family&&<button onClick={()=>selectArea(area!.id)}>{family.name} ×</button>}{subfamily&&<button onClick={()=>selectFamily(area!.id,family!.id)}>{subfamily.name} ×</button>}{type&&<button onClick={()=>selectSubfamily(area!.id,family!.id,subfamily!.id)}>{type.name} ×</button>}<button className="clear-all" onClick={()=>setFilters(emptyCatalogFilters)}>Limpiar todo</button></div>}<div className="catalog-toolbar"><button className="mobile-filter-button" onClick={()=>setFiltersOpen(true)}>☷ Filtrar</button><div><b>{total.toLocaleString("es-ES")} resultados</b><div className="small">Precio y disponibilidad actualizados</div></div><label className="sort-control">Ordenar por<select value={sort} onChange={e=>setSort(e.target.value)}><option value="relevance">Relevancia</option><option value="name">Nombre</option><option value="price-asc">Precio: menor a mayor</option><option value="price-desc">Precio: mayor a menor</option></select></label></div><div className="facet-layout"><aside className={`facet-panel ${filtersOpen?"open":""}`}><div className="facet-head"><div><b>Filtrar por</b><small>Selecciona una opción</small></div><button onClick={()=>setFiltersOpen(false)}>×</button></div><details className="facet-group" open><summary>Departamento</summary><div className="facet-options"><button className={!filters.areaId?"active":""} onClick={()=>setFilters(emptyCatalogFilters)}>Todos <span>{classification.reduce((sum,item)=>sum+item.count,0)}</span></button>{classification.map(item=><button key={item.id} className={filters.areaId===String(item.id)?"active":""} onClick={()=>selectArea(item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>{area&&<details className="facet-group" open><summary>Familia</summary><div className="facet-options">{area.families.map(item=><button key={item.id} className={filters.familyId===String(item.id)?"active":""} onClick={()=>selectFamily(area.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}{family&&<details className="facet-group" open><summary>Subfamilia</summary><div className="facet-options">{family.subfamilies.map(item=><button key={item.id} className={filters.subfamilyId===String(item.id)?"active":""} onClick={()=>selectSubfamily(area!.id,family.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}{subfamily&&<details className="facet-group" open><summary>Tipo de producto</summary><div className="facet-options">{subfamily.product_types.map(item=><button key={item.id} className={filters.productTypeId===String(item.id)?"active":""} onClick={()=>selectType(area!.id,family!.id,subfamily.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}<button className="primary facet-done" onClick={()=>setFiltersOpen(false)}>Ver {total.toLocaleString("es-ES")} productos</button></aside>{filtersOpen&&<button className="facet-backdrop" aria-label="Cerrar filtros" onClick={()=>setFiltersOpen(false)}/>}<section className="catalog-results"><div className="products">{sorted.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd} stockOpen={openStockId===p.id} onStockToggle={open=>setOpenStockId(open?p.id:null)}/>)}</div>{!products.length&&<div className="empty-state"><h2>No encontramos ese material</h2><p>Prueba otra referencia, menos palabras o limpia los filtros aplicados.</p></div>}<div ref={loadMoreRef} className="catalog-load-more" aria-live="polite">{loadingMore?"Cargando más productos…":hasMore?"Desplázate para ver más":`${products.length.toLocaleString("es-ES")} productos mostrados`}</div></section></div></div>
}

function ProductCard({product,onAdd,stockOpen=false,onStockToggle=()=>{}}:{product:Product;onAdd:(id:string,qty?:number)=>void;stockOpen?:boolean;onStockToggle?:(open:boolean)=>void}) { const [qty,setQty]=useState(1); const [imageFailed,setImageFailed]=useState(false); return <article className="product"><div className="product-image-wrap"><span className="product-code">Ref. {product.sku}</span><div className={`product-visual ${imageFailed?"image-missing":""}`}>{!imageFailed?<img src={product.image_url} alt={product.name} loading="lazy" onError={()=>setImageFailed(true)}/>:<><span aria-hidden="true">{product.family.slice(0,2).toUpperCase()}</span><small>{product.family}</small></>}</div></div><div className="product-body"><span className="family-name">{product.family}</span><h3>{product.name}</h3><span className="sku">{product.brand} · Código {product.sku}</span><CatalogPrice withTax={product.price_with_tax} withoutTax={product.price_without_tax} highlightWithoutTax={product.highlight_price_without_tax===true}/><details className="stock-popover" open={stockOpen}><summary className="stock" onClick={event=>{event.preventDefault();onStockToggle(!stockOpen)}} aria-label={`Stock total ${product.total_available} unidades. Abrir detalle por almacén`}><span className="availability-dot"/> {Math.max(0,Math.round(product.total_available))} uds. disponibles <span aria-hidden="true">ⓘ</span></summary><div className="stock-detail"><b>Disponibilidad por almacén</b><small className="stock-help">Pulsa de nuevo en el total para cerrar.</small>{product.stock.length?product.stock.map(item=><div className="stock-row" key={item.store_code}><span>{item.store}<small>Almacén {item.store_code}</small></span><strong>{item.available.toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</strong></div>):<p>Sin existencias en los almacenes incluidos.</p>}<div className="stock-note">No incluye los almacenes configurados como excluidos.</div></div></details><div className="product-actions"><label><span>Uds.</span><QuantityInput className="qty" label={`Cantidad de ${product.name}`} value={qty} onChange={setQty}/></label><button className="secondary block" onClick={()=>onAdd(product.id,qty)}>Añadir al carrito</button></div></div></article> }

type OrderOriginFilter = "ALL" | "WEB" | "NON_WEB";
const isWebOrder=(order:Order)=>order.is_web_order===true||order.origen_pedido==="B2B"||String(order.auxiliary_reference||"").toUpperCase().replace(/\s/g,"").includes("PEDIDOGENERADOWEBB2B");
function OrderOriginMark({order}:{order:Order}) {const web=isWebOrder(order);return <span className={`order-origin-check ${web?"web":"normal"}`}><input type="checkbox" checked={web} readOnly tabIndex={-1} aria-label={web?"Generado por WEB":"No generado por WEB"}/><b>{web?"WEB":"No WEB"}</b></span>}
const matchesOrderOrigin=(order:Order,origin:OrderOriginFilter)=>origin==="ALL"||(origin==="WEB"?isWebOrder(order):!isWebOrder(order));

function MaterialThumbnail({sku}:{sku:string}){
  const [failed,setFailed]=useState(false);
  const [family,setFamily]=useState("Sin clasificar");
  useEffect(()=>{setFailed(false);setFamily("Sin clasificar")},[sku]);
  async function missing(){setFailed(true);try{const response=await fetch(`/api/v1/products/by-sku/${encodeURIComponent(sku)}/visual`,{credentials:"include"});if(response.ok){const data=await response.json();setFamily(data.family||"Sin clasificar")}}catch{}}
  return <span className={`material-thumbnail catalog-thumbnail ${failed?"image-missing":""}`}>
    <span className="thumbnail-reference">Ref. {sku}</span>
    {failed?<span className="thumbnail-placeholder" aria-label={`Sin imagen: ${family}`}><span aria-hidden="true">{family.slice(0,2).toUpperCase()}</span><small>{family}</small></span>:<img src={`/api/v1/products/by-sku/${encodeURIComponent(sku)}/image`} alt={`Material ${sku}`} loading="lazy" decoding="async" onError={()=>void missing()}/>}
  </span>;
}

function Orders({canViewNotes,onOpenNote,showImages,orders,refreshing,onRefresh,onRepeat,onSubmitDraft,onDelete}:{canViewNotes:boolean;onOpenNote:(number:string)=>void;showImages:boolean;orders:Order[];refreshing:boolean;onRefresh:(from?:string,to?:string,state?:string)=>void;onRepeat:(id:string)=>void;onSubmitDraft:(id:string)=>void;onDelete:(id:string)=>void}) {
  const [origin,setOrigin]=useState<OrderOriginFilter>("ALL");
  const visibleOrders=orders.filter(order=>matchesOrderOrigin(order,origin));
  const today=madridDate(new Date()); const [from,setFrom]=useState(today); const [to,setTo]=useState(today); const [state,setState]=useState("PENDIENTE"); const [showDocuments,setShowDocuments]=useState(false);
  const documents=visibleOrders.flatMap(o=>(o.documents||[]).map(d=>({...d,order:o.number}))); const bulkUrl=`/api/v1/documents/download?${new URLSearchParams({date_from:from,date_to:to})}`;
  const documentAction=(d:OrderDocument)=>d.available?<a className="doc-action" href={`/api/v1/documents/${d.type}/${d.id}/file`} target="_blank">Abrir</a>:<span className="status">Registrado</span>;
  return <div className="page orders-page"><div className="section-heading"><div><span className="eyebrow">GESTOR DE FLUJO</span><h1>Mis pedidos</h1><p className="small">Pedidos B2B y EXIT unificados, con prioridad para la información actual de EXIT.</p></div><div className="orders-heading-actions"><button className="ghost" disabled={refreshing} onClick={()=>onRefresh(from,to,state)}>{refreshing?"Actualizando…":"↻ Actualizar pedidos"}</button><button className="ghost" onClick={()=>setShowDocuments(!showDocuments)}>Documentación del resultado ({documents.length})</button></div></div>
  <section className="order-filters"><label>Desde<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>Hasta<input type="date" value={to} onChange={e=>setTo(e.target.value)}/></label><label>Estado<select value={state} onChange={e=>setState(e.target.value)}><option value="TODOS">Todos</option><option value="BORRADOR">Borrador</option><option value="BORRADOR">Borrador</option><option value="PENDIENTE">Pendiente</option><option value="BLOQUEADO">Bloqueado</option><option value="REGISTRADO">Registrado</option><option value="EN_PROCESAMIENTO">En procesamiento</option><option value="PENDIENTE_RECOJO">Pendiente de recojo</option><option value="ENTREGADO">Entregado</option><option value="FACTURADO">Facturado</option></select></label><label>Origen<select value={origin} onChange={e=>setOrigin(e.target.value as OrderOriginFilter)}><option value="WEB">WEB</option><option value="ALL">Todos</option><option value="NON_WEB">No WEB</option></select></label><button className="primary" disabled={refreshing} onClick={()=>onRefresh(from,to,state)}>Consultar</button><span>{visibleOrders.length} pedidos</span></section>
  {showDocuments&&<section className="bulk-documents panel"><div className="section-heading"><h2>Documentación del resultado</h2>{documents.some(d=>d.available)&&<a className="secondary doc-download" href={bulkUrl}>Descargar disponibles (.zip)</a>}</div>{documents.length?documents.map(d=><div className="document-line" key={`${d.type}-${d.id}`}><span><b>{d.type} {d.number}</b><small>Pedido {d.order} · {new Date(d.created_at).toLocaleDateString("es-ES")}</small></span><strong>{money(d.total)}</strong>{documentAction(d)}</div>):<p className="small">No hay documentos para los filtros seleccionados.</p>}</section>}
  <div className="orders-list">{visibleOrders.map(o=>{const isDraft=o.estado_registro_exit==="BORRADOR";const canDelete=!!o.local_order&&(isDraft||o.estado_registro_exit==="PENDIENTE")&&!o.nro_pedido_exit;return <details className="order-card" key={o.id}><summary><span className="order-identifiers"><span className="order-number-origin"><b>{o.exit_number||o.web_number||o.number}</b><OrderOriginMark order={o}/></span>{o.exit_number&&o.web_number&&<small>Pedido web: {o.web_number}</small>}<small>{new Date(o.created_at).toLocaleString("es-ES")} · {o.store}</small></span><span><b>{o.customer}</b><small>Usuario: {o.creator_user_name||o.created_by}</small>{o.principal_user_name&&o.principal_user_name!==(o.creator_user_name||o.created_by)&&<small>Cuenta principal: {o.principal_user_name}</small>}</span><span className={`workflow-badge stage-${visibleOrderStage(o.estado_registro_exit)}`}>{orderStateLabel(visibleOrderStage(o.estado_registro_exit))}</span><strong>{money(o.total)}</strong><span className="order-expand">{isDraft&&o.local_order?<button type="button" className="draft-inline-action" onClick={event=>{event.preventDefault();event.stopPropagation();onSubmitDraft(o.id)}}>Convertir en pendiente</button>:"Ver detalle⌄"}</span></summary><LinePlanningProvider orderId={o.id} customer><div className="order-content"><div className="order-meta"><span><small>Recogida</small><b>{o.pickup_date?new Date(o.pickup_date+"T12:00:00").toLocaleDateString("es-ES"):"Inmediata"}</b></span><span><small>Atender antes de</small><b>{o.attention_deadline_at?deadlineLabel(o.attention_deadline_at):"Sin plazo registrado"}</b></span><span><small>Modalidad</small><b>{o.fulfillment_method==="DELIVERY"?"Delivery":"Recogida en tienda"}</b>{o.delivery_address&&<small>{o.delivery_address}</small>}</span><span><small>Obra</small><b>{o.job_name||"Sin obra"}</b></span><span><small>Referencia</small><b>{o.customer_reference||"—"}</b></span><span><small>Observaciones</small><b>{o.notes||"—"}</b></span><div className="order-actions">{canViewNotes&&(o.exit_number||o.nro_pedido_exit)&&<OrderDeliveryNotes number={o.number} notes={o.delivery_notes} onOpen={onOpenNote}/>} {o.local_order&&<button className="secondary" onClick={()=>onRepeat(o.id)}>Duplicar pedido</button>}{canDelete&&<button className="danger-button" onClick={()=>onDelete(o.id)}>Eliminar</button>}</div></div><div className="workflow">{(o.workflow||[]).map((step,index)=><div className={`workflow-step ${step.completed_at?"complete":""}`} key={step.etapa}><span>{index+1}</span><b>{orderStateLabel(step.etapa)}</b><small>{step.completed_at?(step.date_only?new Date(step.completed_at).toLocaleDateString("es-ES"):new Date(step.completed_at).toLocaleString("es-ES")):"Pendiente"}</small></div>)}</div><div className={`order-lines with-line-planning ${o.exit_number||o.nro_pedido_exit?"exit-order-amounts":""}`}><div className="order-lines-head"><span>Artículo</span><span>Pedida</span><span>Servida</span><span>Precio</span>{(o.exit_number||o.nro_pedido_exit)&&<><span>% descuento</span><span>Importe neto</span></>}<span>Total</span><span>Fecha prevista</span><span>Stock disponible</span><span>Situación / observación</span></div>{(o.items||[]).map((item,index)=>{const served=item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));return <div className="order-line" key={`${o.id}-${item.sku}-${index}`}><span className="material-with-thumbnail">{showImages&&<MaterialThumbnail sku={item.sku}/>}<span><b>{item.description}</b><small>Código {item.sku}</small></span></span><span><b>{units(item.quantity)}</b><small>{item.unit||"UD"}</small></span><span className={served>=item.quantity?"quantity-complete":"quantity-partial"}><b>{units(served)}</b><small>{item.unit||"UD"}</small></span><span>{money(item.unit_price)}</span>{(o.exit_number||o.nro_pedido_exit)&&<><span>{item.discount_pct==null?"—":`${units(item.discount_pct)} %`}</span><span>{item.net_amount==null?"—":money(item.net_amount)}</span></>}<strong>{money(item.line_total)}</strong><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served>=item.quantity} part="date"/><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served>=item.quantity} part="stock"/><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served>=item.quantity} part="note"/></div>})}{!(o.items||[]).length&&<p className="order-lines-empty">Este pedido todavía no tiene líneas disponibles.</p>}</div><OrderHistory order={o}/><div className="order-documents"><h3>Documentación</h3>{o.documents?.length?o.documents.map(d=><div className="document-line" key={d.id}><span><b>{d.type} {d.number}</b><small>{new Date(d.created_at).toLocaleString("es-ES")}</small></span><strong>{money(d.total)}</strong>{documentAction(d)}</div>):<p className="small">Este pedido todavía no tiene documentos asociados.</p>}</div></div></LinePlanningProvider></details>})}</div>{!visibleOrders.length&&<div className="empty-state"><h2>No hay pedidos</h2><p>Cambia el origen, las fechas o el estado seleccionado y pulsa Consultar.</p></div>}</div>
}

function OrderHistory({order}:{order:Order}) {
  if (!order.history_enabled) return null;
  const events=order.history||[];
  return <details className="order-history"><summary>Ver historial de estados</summary><div className="order-history-list">{events.length?events.slice().sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime()).map((event,index)=><div className="order-history-event" key={`${event.estado_registro_exit}-${event.created_at}-${index}`}><span/><div><b>{orderStateLabel(event.estado_registro_exit)}</b><small>{event.source}{event.note?` · ${event.note}`:""}</small></div><time>{event.date_only?new Date(event.created_at).toLocaleDateString("es-ES"):new Date(event.created_at).toLocaleString("es-ES")}</time></div>):<p>No existen cambios registrados.</p>}</div></details>;
}

function Documents({initialNote,showImages,notes,invoices,canViewNotes,canViewInvoices,canViewPrices}:{initialNote?:string;showImages:boolean;notes:DocumentRow[];invoices:DocumentRow[];canViewNotes:boolean;canViewInvoices:boolean;canViewPrices:boolean}) {
  const today=madridDate(new Date()); const previousMonth=new Date(); previousMonth.setMonth(previousMonth.getMonth()-1); const monthAgo=madridDate(previousMonth);
  const [tab,setTab]=useState<"ALBARAN"|"FACTURA">(canViewNotes?"ALBARAN":"FACTURA"); const [noteFilters,setNoteFilters]=useState({number:"",from:monthAgo,to:today}); const [invoiceFilters,setInvoiceFilters]=useState({number:"",from:monthAgo,to:today});
  const [noteState,setNoteState]=useState("TODOS");
  const [linkedNoteError,setLinkedNoteError]=useState(false);
  const [loadedNotes,setLoadedNotes]=useState(notes); const [loadedInvoices,setLoadedInvoices]=useState(invoices); const [loadingDocuments,setLoadingDocuments]=useState(false);
  useEffect(()=>{if(!initialNote)setLoadedNotes(notes)},[notes,initialNote]); useEffect(()=>setLoadedInvoices(invoices),[invoices]);
  const filters=tab==="ALBARAN"?noteFilters:invoiceFilters; const setFilters=tab==="ALBARAN"?setNoteFilters:setInvoiceFilters; const {number,from,to}=filters;
  const rows=tab==="ALBARAN"?loadedNotes:loadedInvoices; const normalizedNumber=number.replace(/[~\/\\-]/g,"").toLowerCase(); const ignoreDates=tab==="FACTURA"&&!!number.trim(); const filtered=rows.filter(row=>{const rowDate=row.created_at?.slice(0,10)||"";const rowNumber=row.number.replace(/[~\/\\-]/g,"").toLowerCase();return(!normalizedNumber||rowNumber.includes(normalizedNumber))&&(ignoreDates||!from||rowDate>=from)&&(ignoreDates||!to||rowDate<=to)&&(tab!=="ALBARAN"||noteState==="TODOS"||(noteState==="FACTURADO"?row.status==="FACTURADO":row.status!=="FACTURADO"))});
  const title=tab==="ALBARAN"?"Albaranes":"Facturas"; const kindPath=tab.toLowerCase(); const exportParams=new URLSearchParams({kind:tab,...number&&{q:number},...!ignoreDates&&from&&{date_from:from},...!ignoreDates&&to&&{date_to:to}});
  const consult=async(target=tab,number=(target==="ALBARAN"?noteFilters.number:invoiceFilters.number))=>{const current=target==="ALBARAN"?noteFilters:invoiceFilters;const params=new URLSearchParams({...number&&{document_number:number},...!(target==="FACTURA"&&number.trim())&&current.from&&{date_from:current.from},...!(target==="FACTURA"&&number.trim())&&current.to&&{date_to:current.to}});setLinkedNoteError(false);setLoadingDocuments(true);try{const result=await api<DocumentRow[]>(`/api/v1/${target==="ALBARAN"?"delivery-notes":"invoices"}?${params}`);if(target==="ALBARAN")setLoadedNotes(result);else setLoadedInvoices(result)}finally{setLoadingDocuments(false)}};
  useEffect(()=>{
    if(!initialNote||!canViewNotes)return;
    const controller=new AbortController();
    setLinkedNoteError(false);setTab("ALBARAN");setNoteFilters({number:initialNote,from:"",to:""});setNoteState("TODOS");setLoadedNotes([]);setLoadingDocuments(true);
    api<DocumentRow[]>(`/api/v1/delivery-notes?${new URLSearchParams({document_number:initialNote})}`,{signal:controller.signal}).then(rows=>{if(!controller.signal.aborted)setLoadedNotes(rows)}).catch(()=>{if(!controller.signal.aborted)setLinkedNoteError(true)}).finally(()=>{if(!controller.signal.aborted)setLoadingDocuments(false)});
    return()=>controller.abort();
  },[initialNote,canViewNotes]);
  const openInvoice=async(number:string)=>{const next={number,from:"",to:""};setInvoiceFilters(next);setTab("FACTURA");await consult("FACTURA",number)};
  return <div className="page documents-page"><div className="section-heading documents-title"><div><span className="eyebrow">DOCUMENTACIÓN EXIT</span><h1>Albaranes y facturas</h1><p className="small">Consulta, descarga o imprime tus documentos comerciales.</p></div></div><div className="document-tabs" role="tablist">{canViewNotes&&<button className={tab==="ALBARAN"?"active":""} onClick={()=>setTab("ALBARAN")}>Albaranes <span>{loadedNotes.length}</span></button>}{canViewInvoices&&<button className={tab==="FACTURA"?"active":""} onClick={()=>setTab("FACTURA")}>Facturas <span>{loadedInvoices.length}</span></button>}</div><section className="document-toolbar"><label>{tab==="ALBARAN"?"Número de albarán":"Número de factura"}<input maxLength={20} size={20} value={filters.number} onChange={event=>setFilters({...filters,number:event.target.value})} placeholder={tab==="ALBARAN"?"Ej. 2026-AL-12345":"Ej. 2026-FR-12345"}/></label><label>Desde<input type="date" value={from} onChange={event=>setFilters({...filters,from:event.target.value})}/></label><label>Hasta<input type="date" value={to} onChange={event=>setFilters({...filters,to:event.target.value})}/></label>{tab==="ALBARAN"&&<label>Estado (opcional)<select value={noteState} onChange={event=>setNoteState(event.target.value)}><option value="TODOS">Todos</option><option value="FACTURADO">Facturado</option><option value="NO_FACTURADO">No facturado</option></select></label>}<button className="primary document-consult" disabled={loadingDocuments} onClick={()=>consult()}>{loadingDocuments?"Consultando…":"Consultar"}</button><div className="document-toolbar-actions">{canViewPrices&&<a className="secondary" href={`/api/v1/documents/export?${exportParams}`}>Descargar Excel</a>}<button className="ghost" onClick={()=>window.print()}>Imprimir listado</button></div></section><div className="document-list-heading"><div><h2>{title}</h2><span>{filtered.length} documentos</span></div><strong>{money(canViewPrices?filtered.reduce((sum,row)=>sum+(row.total??0),0):null)}</strong></div><div className="document-cards">{linkedNoteError&&<p role="alert">No se pudo consultar el albarán. Pulsa Consultar para reintentar.</p>}{filtered.map(row=><details className={`document-card ${tab==="FACTURA"?"invoice-card":""}`} key={row.id}><summary><span className="document-main"><small>{tab}</small><b>{row.number}</b><em>{row.created_at?new Date(row.created_at).toLocaleDateString("es-ES"):"Sin fecha"}</em></span>{tab==="ALBARAN"&&<span><small>Estado</small><b className="document-status">{deliveryNoteStateLabel(row.status)}</b></span>}<span><small>{tab==="ALBARAN"?"Pedido":"Vencimiento"}</small><b>{tab==="ALBARAN"?(row.order_number||"—"):(row.due_date?new Date(row.due_date).toLocaleDateString("es-ES"):"—")}</b></span><strong>{money(row.total)}</strong><span className="document-expand">Ver detalle⌄</span></summary><div className="document-detail"><div><small>Delegación</small><b>{row.store_name||"No disponible"}</b></div><div><small>Base imponible</small><b>{money(canViewPrices?(row.subtotal||0):null)}</b></div><div><small>IVA</small><b>{money(canViewPrices?(row.tax_total||0):null)}</b></div><div><small>Total</small><b>{money(row.total)}</b></div>{canViewInvoices&&row.invoice_number&&<div><small>Factura relacionada</small><button className="invoice-link" onClick={()=>openInvoice(row.invoice_number!)}>{row.invoice_number}</button></div>}{row.document&&<div><small>Documento EXIT</small><b>{row.document}</b></div>}{canViewPrices&&<a className="primary document-download" href={`/api/v1/documents/${tab}/${row.id}/file`}>Descargar PDF</a>}</div>{tab==="ALBARAN"&&<div className="delivery-items"><div className="delivery-items-head"><span>Artículo</span><span>Delegación</span><span>Cantidad</span><span>Precio</span><span>% descuento</span><span>Precio neto</span><span>Total</span></div>{(row.items||[]).map(item=><div className="delivery-item" key={`${row.id}-${item.line}`}><span className="material-with-thumbnail">{showImages&&<MaterialThumbnail sku={item.sku}/>}<span><b>{item.description||"Artículo sin descripción"}</b><small>Código {item.sku} · Línea {item.line}</small></span></span><span>{item.dispatch_delegation||row.store_name||"No disponible"}</span><span><b>{units(item.quantity)}</b> {item.unit||"UD"}</span><span>{money(item.unit_price)}</span><span>{item.discount_pct==null?"••••":`${units(item.discount_pct)} %`}</span><span>{money(item.net_amount)}</span><strong>{money(item.total)}</strong></div>)}{!(row.items||[]).length&&<p className="delivery-empty">El albarán no contiene líneas de material.</p>}</div>}</details>)}{!filtered.length&&<div className="empty-state"><h2>No hay {kindPath === "albaran" ? "albaranes" : "facturas"}</h2><p>Cambia el número o el rango de fechas y pulsa Consultar.</p></div>}</div></div>
}

function PasswordSettings(){
  const [currentPassword,setCurrentPassword]=useState(""); const [newPassword,setNewPassword]=useState(""); const [confirmation,setConfirmation]=useState("");
  const [message,setMessage]=useState(""); const [passwordError,setPasswordError]=useState(""); const [saving,setSaving]=useState(false);
  const submit=async(event:FormEvent)=>{event.preventDefault();setMessage("");setPasswordError("");if(newPassword!==confirmation){setPasswordError("Las contraseñas nuevas no coinciden");return}setSaving(true);try{await api("/api/v1/account/password",{method:"PATCH",body:JSON.stringify({current_password:currentPassword,new_password:newPassword})});setCurrentPassword("");setNewPassword("");setConfirmation("");setMessage("Contraseña actualizada correctamente")}catch(error){setPasswordError((error as Error).message)}finally{setSaving(false)}};
  return <form className="section password-form" onSubmit={submit}><h2>Cambiar contraseña</h2><p className="small">Introduce tu contraseña actual y confirma la nueva contraseña de acceso a la web.</p><label>Contraseña actual<input type="password" autoComplete="current-password" value={currentPassword} onChange={event=>setCurrentPassword(event.target.value)} required/></label><label>Nueva contraseña<input type="password" autoComplete="new-password" minLength={6} value={newPassword} onChange={event=>setNewPassword(event.target.value)} required/></label><label>Repetir nueva contraseña<input type="password" autoComplete="new-password" minLength={6} value={confirmation} onChange={event=>setConfirmation(event.target.value)} required/></label>{passwordError&&<div className="form-error" role="alert">{passwordError}</div>}{message&&<div className="form-success" role="status">{message}</div>}<button className="primary" disabled={saving}>{saving?"Guardando…":"Actualizar contraseña"}</button></form>
}

function Account({user,customer,onPreferences}:{user:User;customer:AccountCustomer|null;onPreferences:(preferences:{show_delivery_note_images:boolean;show_order_images:boolean})=>void}) {
  const [noteImages,setNoteImages]=useState(!!user.show_delivery_note_images),[orderImages,setOrderImages]=useState(!!user.show_order_images);
  const [preferencesBusy,setPreferencesBusy]=useState(false),[preferencesMessage,setPreferencesMessage]=useState(""),[preferencesError,setPreferencesError]=useState("");
  async function savePreferences(event:FormEvent){event.preventDefault();setPreferencesBusy(true);setPreferencesError("");setPreferencesMessage("");try{const result=await api<{show_delivery_note_images:boolean;show_order_images:boolean}>("/api/v1/account/preferences",{method:"PATCH",body:JSON.stringify({show_delivery_note_images:noteImages,show_order_images:orderImages})});onPreferences(result);setPreferencesMessage("Preferencias guardadas")}catch(e){setPreferencesError((e as Error).message)}finally{setPreferencesBusy(false)}}
  const [accountTab,setAccountTab]=useState("data");
  const isCustomer=user.role!=="ADMIN"&&user.role!=="OPERADOR_TIENDA";
  const accountTabs=[
    {id:"data",label:"Mis datos"},
    ...(user.can_manage_preferences!==false?[{id:"preferences",label:"Preferencias"}]:[]),
    {id:"password",label:"Contraseña"},
    ...(isCustomer?[{id:"qr",label:"Acceso QR"}]:[]),
    ...(user.can_manage_subusers?[{id:"subusers",label:"Subusuarios"}]:[]),
  ];
  const activeTab=accountTabs.some(tab=>tab.id===accountTab)?accountTab:"data";
  return <div className="page account-page"><h1>Mi cuenta</h1><p className="small">Consulta tus datos y gestiona cada opción desde su pestaña.</p><div className="account-tabs" role="tablist" aria-label="Opciones de Mi cuenta">{accountTabs.map((tab,index)=><button type="button" role="tab" id={`account-tab-${tab.id}`} aria-controls={`account-panel-${tab.id}`} aria-selected={activeTab===tab.id} tabIndex={activeTab===tab.id?0:-1} key={tab.id} onClick={()=>setAccountTab(tab.id)} onKeyDown={event=>{let next=index;if(event.key==="ArrowRight")next=(index+1)%accountTabs.length;else if(event.key==="ArrowLeft")next=(index-1+accountTabs.length)%accountTabs.length;else if(event.key==="Home")next=0;else if(event.key==="End")next=accountTabs.length-1;else return;event.preventDefault();setAccountTab(accountTabs[next].id);event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus()}}>{tab.label}</button>)}</div>
    <div className="account-tab-panel" role="tabpanel" id="account-panel-data" aria-labelledby="account-tab-data" hidden={activeTab!=="data"} tabIndex={0}><section className="section"><h2>{customer?.trade_name||customer?.legal_name||user.name}</h2><p>Razón social: <b>{customer?.legal_name||"—"}</b></p><p>Código cliente EXITERP: <b>{customer?.erp_id||"—"}</b></p><p>NIF/CIF: {customer?.tax_id||"—"}</p><p>Dirección de facturación: {customer?.billing_address||"—"}</p><p>Contacto ERP: {customer?.email||customer?.phone||"—"}</p><p>Nombre del usuario: <b>{user.login_name||user.name}</b></p>{user.is_subuser&&<p>Cuenta principal: <b>{user.principal_user_name}</b></p>}<p>Código de acceso: <b>{user.access_code||customer?.erp_id||"—"}</b></p><p>Correo de acceso: <b>{user.email}</b></p>{user.contact_phone&&<p>Teléfono del usuario: <b>{user.contact_phone}</b></p>}<small className="account-source">Los datos comerciales se consultan directamente en EXIT.</small></section></div>
    {user.can_manage_preferences!==false&&<div className="account-tab-panel" role="tabpanel" id="account-panel-preferences" aria-labelledby="account-tab-preferences" hidden={activeTab!=="preferences"} tabIndex={0}><form className="section display-preferences" onSubmit={savePreferences}><h2>Preferencias de visualización</h2><p>Elige si quieres ver miniaturas junto a los materiales. Si desactivas una opción, se muestra solo el texto.</p><label><input type="checkbox" checked={noteImages} onChange={event=>setNoteImages(event.target.checked)}/> Miniaturas en albaranes</label><label><input type="checkbox" checked={orderImages} onChange={event=>setOrderImages(event.target.checked)}/> Miniaturas en pedidos</label>{preferencesError&&<p className="error" role="alert">{preferencesError}</p>}{preferencesMessage&&<p role="status">{preferencesMessage}</p>}<button className="primary" disabled={preferencesBusy}>{preferencesBusy?"Guardando…":"Guardar preferencias"}</button></form></div>}
    <div className="account-tab-panel" role="tabpanel" id="account-panel-password" aria-labelledby="account-tab-password" hidden={activeTab!=="password"} tabIndex={0}><PasswordSettings/></div>
    {isCustomer&&<div className="account-tab-panel" role="tabpanel" id="account-panel-qr" aria-labelledby="account-tab-qr" hidden={activeTab!=="qr"} tabIndex={0}><AccountQr/></div>}
    {user.can_manage_subusers&&<div className="account-tab-panel" role="tabpanel" id="account-panel-subusers" aria-labelledby="account-tab-subusers" hidden={activeTab!=="subusers"} tabIndex={0}><Subusers/></div>}
  </div>
}

function CartDrawer({cart,stores,onClose,onContinue,onUpdate,onRemove,onCheckout}:{cart:Cart;stores:Store[];onClose:()=>void;onContinue:()=>void;onUpdate:(id:number,q:number)=>void;onRemove:(id:number)=>void;onCheckout:(s:string,j:string,r:string,n:string,d:boolean,p:string,f:string,a:string)=>void}) { const [store,setStore]=useState(cart.store?.id||stores[0]?.id||""); const [job,setJob]=useState(""); const [ref,setRef]=useState(""); const [notes,setNotes]=useState(""); const [draft,setDraft]=useState(false); const [delivery,setDelivery]=useState(false); const [address,setAddress]=useState(""); const [scheduled,setScheduled]=useState(false); const manualSchedule=useRef(false); const [pickup,setPickup]=useState(""); const [config,setConfig]=useState<{preparation_minutes:number;minimum_date:string|null;immediate_available:boolean;immediate_ready_at:string|null}|null>(null); const [configError,setConfigError]=useState(""); const [scheduledDeadline,setScheduledDeadline]=useState<string|null>(null); const [deadlineError,setDeadlineError]=useState(""); useEffect(()=>{let active=true;setScheduledDeadline(null);setDeadlineError("");if(!scheduled||!pickup)return;const selectedStore=stores.find(row=>row.id===store);if(!selectedStore)return;api<{scheduled_ready_at:string|null}>(`/api/v1/pickup-availability?${new URLSearchParams({company:String(selectedStore.company_code),delegation:selectedStore.code,scheduled_date:pickup})}`).then(value=>{if(active){setScheduledDeadline(value.scheduled_ready_at);if(!value.scheduled_ready_at)setDeadlineError("No hay un horario que permita preparar el pedido en esta fecha.")}}).catch(error=>{if(active)setDeadlineError((error as Error).message)});return()=>{active=false}},[scheduled,pickup,store,stores]); useEffect(()=>{let active=true;async function check(){const selectedStore=stores.find(row=>row.id===store);if(!selectedStore)return;try{const value=await api<{preparation_minutes:number;minimum_date:string|null;immediate_available:boolean;immediate_ready_at:string|null}>(`/api/v1/pickup-availability?${new URLSearchParams({company:String(selectedStore.company_code),delegation:selectedStore.code})}`);if(active){setConfig(value);setPickup(old=>value.minimum_date?(old&&old>=value.minimum_date?old:value.minimum_date):"");if(!value.immediate_available)setScheduled(true);else if(!manualSchedule.current)setScheduled(false);setConfigError("")}}catch(e){if(active){setConfig(null);setConfigError((e as Error).message)}}}setConfig(null);setPickup("");manualSchedule.current=false;void check();const timer=setInterval(check,30000);return()=>{active=false;clearInterval(timer)}},[store,stores]); return <><div className="drawer-back" onClick={onClose}/><aside className="drawer"><div className="drawer-head"><div><div className="small">PEDIDO EN PREPARACIÓN</div><h2>Tu pedido</h2></div><button className="close" aria-label="Cerrar carrito" onClick={onClose}>×</button></div><button className="secondary block cart-continue" onClick={onContinue}>← Seguir comprando</button><div className="cart-lines">{cart.items.map(item=><div className="cart-line" key={item.id}><div><b>{item.name}</b><div className="small">{item.sku} · {money(item.unit_price)} por unidad</div><strong className="cart-line-total">{money(item.line_total)}</strong></div><QuantityInput label={`Cantidad de ${item.name}`} value={item.quantity} onChange={quantity=>onUpdate(item.id,quantity)}/><button className="ghost" aria-label={`Eliminar ${item.name}`} onClick={()=>onRemove(item.id)}>×</button></div>)}</div><div className="cart-totals"><div><span>Subtotal sin IVA</span><strong>{money(cart.subtotal)}</strong></div><div><span>IVA</span><strong>{money(cart.tax_total)}</strong></div><div className="cart-grand-total"><span>Total con IVA</span><strong>{money(cart.total)}</strong></div></div><label className="label">{cart.delivery_enabled&&delivery?"Sede de preparación":"Recoger en"}</label><select className="select" value={store} onChange={e=>setStore(e.target.value)}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select>{config&&!config.immediate_available&&<p className="small">Recogida inmediata no disponible. El pedido se enviará para el siguiente día hábil de esta sede. Puedes revisar la fecha en Datos adicionales.</p>}{!(cart.delivery_enabled&&delivery)&&<p className="small">El pedido preparado se conservará durante 24 horas. Pasado ese plazo, se eliminará si no lo recoges.</p>}<details className="cart-additional"><summary>Datos adicionales <span>(opcional)</span></summary><div className="cart-additional-fields">{cart.delivery_enabled&&<><label className="label">Modalidad de entrega</label><select className="select" aria-label="Modalidad de entrega" value={delivery?"DELIVERY":"PICKUP"} onChange={e=>setDelivery(e.target.value==="DELIVERY")}><option value="PICKUP">Recogida en tienda</option><option value="DELIVERY">Delivery</option></select>{delivery&&<><label className="label">Dirección de delivery</label><textarea className="textarea" aria-label="Dirección de delivery" maxLength={500} value={address} onChange={e=>setAddress(e.target.value)}/><p className="small">El plazo de atención indica cuándo quedará preparado el pedido; no es la hora de llegada del reparto.</p></>}</>}<label className="label">{delivery&&cart.delivery_enabled?"Cuándo preparar":"Cuándo recoger"}</label><select className="select" value={scheduled?"scheduled":"immediate"} onChange={e=>{manualSchedule.current=true;const programmed=e.target.value==="scheduled";setScheduled(programmed);if(programmed&&config?.minimum_date)setPickup(config.minimum_date)}}>{config?.immediate_available&&<option value="immediate">Inmediata</option>}<option value="scheduled">Programada</option></select>{configError&&<p role="alert" className="error">{configError}</p>}{scheduled?<><label className="label">{cart.delivery_enabled&&delivery?"Fecha de preparación":"Fecha de recogida"}</label><input className="input" aria-label="Fecha de recogida" type="date" min={config?.minimum_date||undefined} value={pickup||config?.minimum_date||""} onChange={e=>setPickup(e.target.value||config?.minimum_date||"")}/>{scheduledDeadline&&<p className="attention-deadline">Límite de atención: <b>{deadlineLabel(scheduledDeadline)}</b><small>Apertura de la sede + {config?.preparation_minutes} minutos de preparación.</small></p>}{deadlineError&&<p className="error" role="alert">{deadlineError}</p>}{config&&!config.minimum_date&&<p className="error" role="alert">Esta sede no tiene ningún día de atención configurado. Contacta con la tienda.</p>}</>:<p className="small">{config?`Tiempo de preparación: ${config.preparation_minutes} minutos. Límite de atención: ${config.immediate_ready_at?deadlineLabel(config.immediate_ready_at):"—"}, dentro del horario de atención.`:"Consultando tiempo de preparación…"}</p>}<label className="label">Obra</label><input className="input" value={job} onChange={e=>setJob(e.target.value)} placeholder="Reforma Hotel Coruña"/><label className="label">Referencia cliente</label><input className="input" value={ref} onChange={e=>setRef(e.target.value)} placeholder="OBRA-324"/><label className="label">Observaciones</label><textarea className="textarea" rows={3} value={notes} onChange={e=>setNotes(e.target.value)}/></div></details><label className="draft-check"><input type="checkbox" checked={draft} onChange={e=>setDraft(e.target.checked)}/><span><b>Guardar como borrador</b><small>Podrás revisarlo y enviarlo después desde Mis pedidos.</small></span></label><button className="primary block" disabled={!cart.items.length||!store||!config||(cart.delivery_enabled&&delivery&&!address.trim())||(scheduled&&(!config.minimum_date||((pickup||config.minimum_date)<config.minimum_date)))} onClick={()=>onCheckout(store,job,ref,notes,draft,scheduled?(pickup||config?.minimum_date||""):"",cart.delivery_enabled&&delivery?"DELIVERY":"PICKUP",cart.delivery_enabled&&delivery?address:"")}>{draft?"Guardar borrador":"Enviar pedido a tienda"}</button><button className="secondary block cart-continue" onClick={onContinue}>← Seguir comprando</button></aside></> }

function OrderConfirmation({order,onClose,onViewOrders}:{order:Order;onClose:()=>void;onViewOrders:()=>void}) {
  const draft=order.estado_registro_exit==="BORRADOR"; const warning=order.stock_warning;
  return <div className="confirmation-back" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="order-confirmation" role="dialog" aria-modal="true" aria-labelledby="confirmation-title"><button className="confirmation-close" aria-label="Cerrar" onClick={onClose}>×</button><div className="confirmation-icon" aria-hidden="true">✓</div><span className="eyebrow">{draft?"BORRADOR GUARDADO":"PEDIDO REGISTRADO"}</span><h2 id="confirmation-title">{draft?"Borrador guardado":"¡Pedido recibido!"}</h2><p>{draft?"El pedido todavía no se ha enviado a la tienda. Puedes revisarlo y enviarlo desde Mis pedidos.":<>Hemos enviado tu solicitud a <b>{order.store}</b>. Podrás seguir cada paso desde Mis pedidos.</>}</p>{!draft&&order.pickup_date&&<p className="confirmation-stock-warning">El pedido se enviará para recogida el <b>{new Date(order.pickup_date+"T12:00:00").toLocaleDateString("es-ES")}</b>, según la programación seleccionada.</p>}{!draft&&order.attention_deadline_at&&<p className="attention-deadline"><b>Límite de atención: {deadlineLabel(order.attention_deadline_at)}</b></p>}{!draft&&<p className="confirmation-stock-warning"><b>Importante:</b> El pedido preparado solo se conservará durante 24 horas. Después de ese plazo, se eliminará si no lo recoges.</p>}{warning&&<div className="confirmation-stock-warning"><b>Stock insuficiente en {warning.store}</b><p>El pedido se ha registrado, pero estos materiales podrían no estar disponibles para recoger el mismo día. Revisaremos si pueden atenderse desde otras delegaciones.</p>{warning.items.map(item=><span key={item.sku}><strong>{item.sku}</strong> {item.name}<small>Pedido: {units(item.requested)} · Disponible: {units(item.available)}</small></span>)}</div>}<p className="small">{order.fulfillment_method==="DELIVERY"?`Delivery · ${order.delivery_address||""}`:"Recogida en tienda"}</p><div className="confirmation-number"><small>Número de pedido</small><strong>{order.number}</strong></div><div className="confirmation-summary"><span><small>Artículos</small><b>{order.items?.length||0}</b></span><span><small>Total con IVA</small><b>{money(order.total)}</b></span><span><small>Estado</small><b>{draft?"Borrador":"Registrado"}</b></span></div><div className="confirmation-next"><b>{draft?"Siguiente paso":"¿Qué ocurre ahora?"}</b><span>{draft?"Pulsa “Quitar borrador y enviar” cuando el pedido esté listo.":"La tienda revisará el pedido y cambiará su estado cuando entre en preparación."}</span></div><div className="confirmation-actions"><button className="ghost" onClick={onClose}>Seguir comprando</button><button className="primary" onClick={onViewOrders}>Ver mis pedidos</button></div></section></div>
}

function displayOrderNumber(order:Order) { return order.nro_pedido_exit?.split("/").pop()||order.number.replace(/^EXIT-[^-]*-[^-]*-/,""); }
function orderNumberValue(order:Order) { const value=displayOrderNumber(order); const numeric=Number(value.replace(/\D/g,"")); return Number.isFinite(numeric)?numeric:0; }

function CommandItems({order}:{order:Order}) {
  const [showSga,setShowSga]=useState(false);
  const servedQuantity=(item:OrderLine)=>item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));
  const pending=(item:OrderLine)=>Math.max(0,item.quantity-servedQuantity(item));
  const uniqueCount=(items:OrderLine[])=>new Set(items.map(item=>item.sku)).size;
  const renderItems=(items:OrderLine[])=><>{items.map((item,index)=>{const served=servedQuantity(item)>=item.quantity;return <div className={`dispatch-line with-line-planning ${served?"is-served":""}`} key={`${order.id}-${item.fulfillment_zone}-${item.sku}-${index}`}><b>{item.sku}</b><span>{item.description}</span><strong>{served?<em>SERVIDO</em>:<><em>PENDIENTE</em><small>{pending(item).toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</small></>}</strong><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served} part="date"/><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served} part="stock"/><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served} part="note"/></div>})}{!items.length&&<p className="dispatch-empty">Sin materiales en esta zona</p>}</>;
  const kardex=(order.items||[]).filter(item=>item.fulfillment_zone==="KARDEX");
  const sga=(order.items||[]).filter(item=>item.fulfillment_zone!=="KARDEX");
  const sgaReferences=sga.length;
  const sgaServed=sga.filter(item=>servedQuantity(item)>=item.quantity).length;
  const sgaProgress=sgaReferences?Math.round(sgaServed/sgaReferences*100):0;
  const zoneHeader=(label:string,items:OrderLine[])=><header><h3>{label}</h3><span>{uniqueCount(items)} referencias</span></header>;
  return <LinePlanningProvider orderId={order.id}><OrderLinePlanning orderId={order.id}/><div className="dispatch-zones"><section className="dispatch-zone zone-KARDEX">{zoneHeader("KARDEX",kardex)}<div className="dispatch-columns with-line-planning"><small>Código</small><small>Material</small><small>Estado</small><small>Fecha prevista</small><small>Stock disponible</small><small>Situación / observación</small></div><div className="dispatch-lines">{renderItems(kardex)}</div><footer>Tipos de material <b>{uniqueCount(kardex)}</b></footer></section><div className="dispatch-card-footer"><OrderOriginMark order={order}/><OrderDeliveryNotes number={displayOrderNumber(order)} notes={order.delivery_notes}/><button className="sga-popup-trigger" disabled={!sga.length} onClick={()=>setShowSga(true)}>SGA</button></div></div>{showSga&&<div className="sga-modal-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setShowSga(false)}}><section className="sga-modal" role="dialog" aria-modal="true" aria-label={`Materiales SGA del pedido ${displayOrderNumber(order)}`}><header><div><small>Pedido {displayOrderNumber(order)}</small><h2>SGA</h2></div><button aria-label="Cerrar" onClick={()=>setShowSga(false)}>×</button></header><div className="sga-service-progress"><b>Servido SGA</b><span>{sgaServed}/{sgaReferences}</span><progress max={100} value={sgaProgress} aria-label="Líneas servidas de SGA"/><strong>{sgaProgress}%</strong></div><div className="dispatch-columns with-line-planning"><small>Código</small><small>Material</small><small>Estado</small><small>Fecha prevista</small><small>Stock disponible</small><small>Situación / observación</small></div><div className="dispatch-lines">{renderItems(sga)}</div><footer>{sga.length} líneas SGA</footer></section></div>}</LinePlanningProvider>
}

function ExitOrderDialog({order,busy,error,onCancel,onSave}:{order:Order;busy:boolean;error:string;onCancel:()=>void;onSave:(number:string,registeredAt:string)=>Promise<void>}){
  const dialog=useRef<HTMLDialogElement>(null);
  const [number,setNumber]=useState(order.nro_pedido_exit||"");
  const [registeredAt,setRegisteredAt]=useState(()=>{
    const value=new Date(order.fecha_registro_exit||order.server_now||Date.now());
    const parts=new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Madrid",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"}).format(value);
    return parts.replace(" ","T");
  });
  useEffect(()=>{dialog.current?.showModal();return()=>dialog.current?.close()},[]);
  return <dialog ref={dialog} className="exit-order-dialog" aria-labelledby="exit-order-dialog-title" onCancel={event=>{event.preventDefault();if(!busy)onCancel()}}><form onSubmit={event=>{event.preventDefault();if(number.trim()&&registeredAt&&!busy)void onSave(number.trim(),registeredAt)}}><header><div><small>Pedido WEB {order.number}</small><h2 id="exit-order-dialog-title">Vincular pedido EXIT</h2></div><button type="button" className="ghost" aria-label="Cerrar" disabled={busy} onClick={onCancel}>×</button></header><p>Introduce los datos del pedido creado manualmente en EXIT. Se guardará como Registrado y se añadirá al historial.</p><label htmlFor="exit-order-number">Número de pedido EXIT</label><input id="exit-order-number" autoFocus required maxLength={80} disabled={busy} value={number} onChange={event=>setNumber(event.target.value)} placeholder="Ej. 2026/AL/6007081" autoComplete="off"/><small className="small">Introduce preferiblemente el número completo del pedido.</small><label htmlFor="exit-order-registered-at">Fecha y hora de registro en EXIT</label><input id="exit-order-registered-at" type="datetime-local" step={1} required disabled={busy} value={registeredAt} onChange={event=>setRegisteredAt(event.target.value)}/><small className="small">Hora de la sede (Europe/Madrid). Indica la fecha y hora reales que figuran en EXIT.</small>{error&&<p className="error" role="alert">{error}</p>}<footer><button type="button" className="secondary" disabled={busy} onClick={onCancel}>Cancelar</button><button type="submit" className="primary" disabled={busy||!number.trim()||!registeredAt}>{busy?"Guardando…":"Guardar vínculo"}</button></footer></form></dialog>
}

function OperatorWebOrders({orders,onDelivered}:{orders:Order[];onDelivered:()=>Promise<void>}) {
  const [openedNote,setOpenedNote]=useState<{orderId:string;number:string}|null>(null);
  const [busy,setBusy]=useState<string|null>(null),[error,setError]=useState("");
  const [serverNow,setServerNow]=useState<number|null>(null);
  useEffect(()=>{
    const stamp=orders.map(order=>Date.parse(order.server_now||"")).find(Number.isFinite);
    if(stamp==null){setServerNow(null);return}
    const started=performance.now();
    const tick=()=>setServerNow(stamp+performance.now()-started);
    tick();const timer=window.setInterval(tick,1000);
    return()=>window.clearInterval(timer);
  },[orders]);
  const [registerOrder,setRegisterOrder]=useState<Order|null>(null);
  const [deleteCandidate,setDeleteCandidate]=useState<Order|null>(null);
  async function registration(order:Order,state:"PENDIENTE"|"REGISTRADO",number:string|null=null,registeredAt:string|null=null){
    if(state==="PENDIENTE"&&!window.confirm(state==="PENDIENTE"?`¿Devolver ${order.number} a Pendiente? Se quitará el vínculo EXIT, la fecha de entrega y las cantidades servidas. El robot podrá procesarlo nuevamente.`:`¿Marcar ${order.number} como Registrado y vincularlo a EXIT ${number}?`))return;
    setBusy(order.id);setError("");try{await api(`/api/v1/store/orders/${order.id}/registration`,{method:"PATCH",body:JSON.stringify({state,exit_order_number:number,...(registeredAt&&{exit_registered_at:registeredAt})})});setRegisterOrder(null);await onDelivered()}catch(e){setError((e as Error).message)}finally{setBusy(null)}
  }
  async function remove(order:Order){await api(`/api/v1/store/orders/${order.id}`,{method:"DELETE"});setDeleteCandidate(null);try{await onDelivered()}catch(e){setError((e as Error).message)}}
  async function deliver(order:Order){if(!window.confirm(`¿Confirmar la entrega del pedido ${order.nro_pedido_exit||order.number}? Se guardarán la fecha y hora actuales.`))return;setBusy(order.id);setError("");try{await api("/api/v1/store/orders/delivery",{method:"POST",body:JSON.stringify({order_id:order.delivery_order_id||order.id,order_date:order.created_at.slice(0,10)})});await onDelivered()}catch(e){setError((e as Error).message)}finally{setBusy(null)}}
  return <>{openedNote&&<OperatorDeliveryNote orderId={openedNote.orderId} number={openedNote.number} onClose={()=>setOpenedNote(null)}/>} {deleteCandidate&&<DeleteOrderDialog order={deleteCandidate} onCancel={()=>setDeleteCandidate(null)} onConfirm={()=>remove(deleteCandidate)}/>} {registerOrder&&<ExitOrderDialog order={registerOrder} busy={busy!==null} error={error} onCancel={()=>{setRegisterOrder(null);setError("")}} onSave={(number,registeredAt)=>registration(registerOrder,"REGISTRADO",number,registeredAt)}/>}<div className="operator-web-list">{error&&<p className="error" role="alert">{error}</p>}{orders.map(order=><details className="operator-web-order" key={order.id}><summary><span className="order-identifiers"><b>{order.nro_pedido_exit||order.number}</b>{order.nro_pedido_exit&&<small>Pedido WEB: {order.number}</small>}{order.fecha_registro_exit&&<small>Registro EXIT: {deadlineLabel(order.fecha_registro_exit)}</small>}<small>{order.store}</small></span><span><b>{order.customer}</b><small>Código {order.customer_code||"—"} · {order.created_by||"EXIT"}</small></span><span className={`workflow-badge stage-${visibleOrderStage(order.estado_registro_exit)}`}>{orderStateLabel(order.estado_registro_exit||"PENDIENTE")}</span><span><b>{(order.items||[]).length} líneas</b><small>{new Set((order.items||[]).map(item=>item.sku)).size} referencias</small></span><span className="order-pickup-summary"><span className="pickup-labels"><span className="pickup-kind" title={order.fulfillment_method==="DELIVERY"?order.delivery_address||"Delivery":"Recogida en tienda"}>{order.fulfillment_method==="DELIVERY"?"Delivery":"Recogida en tienda"}</span><span className={`pickup-kind ${order.pickup_date?"scheduled":"immediate"}`}>{order.pickup_date?"▦ Programada":"ϟ Inmediata"}</span></span><OrderDeliveryDeadline order={order} now={serverNow}/><span className="actual-delivery"><small>{order.fulfillment_method==="DELIVERY"?"Entrega real":"Recogida real"}</small><b>{order.delivered_at?deadlineLabel(order.delivered_at):"—"}</b></span></span><span className="order-expand order-header-actions"><OrderDeliveryNotes number={displayOrderNumber(order)} notes={order.delivery_notes} onOpen={number=>setOpenedNote({orderId:order.id,number})}/>{order.estado_registro_exit==="ATENDIDO"&&!order.delivered_at&&<button type="button" className="primary" disabled={busy!==null} onClick={event=>{event.preventDefault();event.stopPropagation();void deliver(order)}}>{busy===order.id?"Guardando…":"Entregar"}</button>}<span>Ver detalle⌄</span></span></summary><div className="operator-web-detail">{order.fulfillment_method==="DELIVERY"&&<p><b>Delivery:</b> {order.delivery_address}</p>}<PickupEditor order={order} onSaved={onDelivered}/><div className="web-order-origin"><b>PEDIDO WEB</b><span>{order.auxiliary_reference}</span><span className="web-order-change" role="group" aria-label="Cambiar estado del pedido"><span>Gestión:</span>{order.estado_registro_exit!=="PENDIENTE"&&<button className="primary" disabled={busy!==null||!["REGISTRADO","BLOQUEADO"].includes(order.estado_registro_exit||"")||!!order.delivered_at} title={["REGISTRADO","BLOQUEADO"].includes(order.estado_registro_exit||"")?"Volver a pendiente":"Disponible solo en Registrado o Bloqueado"} onClick={()=>void registration(order,"PENDIENTE")}>Pendiente</button>}{["PENDIENTE","BLOQUEADO"].includes(order.estado_registro_exit||"")&&<button className="primary" disabled={busy!==null} onClick={()=>{setError("");setRegisterOrder(order)}}>Vincular EXIT</button>}</span>{order.estado_registro_exit==="PENDIENTE"&&!order.nro_pedido_exit&&<button className="secondary" disabled={busy!==null} onClick={()=>setDeleteCandidate(order)}>Eliminar pedido</button>}{order.estado_registro_exit==="PENDIENTE"&&<span>Pendiente de registro en EXIT.</span>}</div><OrderHistory order={order}/><LinePlanningProvider orderId={order.id}><OrderLinePlanning orderId={order.id}/><div className="web-order-lines with-line-planning"><div className="web-order-lines-head"><span>Artículo</span><span>Zona</span><span>Pedida</span><span>Servida</span><span>Estado</span><span>Fecha prevista</span><span>Stock disponible</span><span>Situación / observación</span></div>{(order.items||[]).map((item,index)=>{const served=item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));return <div className="web-order-line" key={`${order.id}-${item.sku}-${index}`}><span><b>{item.description}</b><small>{item.sku}</small></span><span>{item.fulfillment_zone||"SGA"}</span><span>{units(item.quantity)}</span><span>{units(served)}</span><strong>{served>=item.quantity?"SERVIDO":"PENDIENTE"}</strong><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served>=item.quantity} part="date"/><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served>=item.quantity} part="stock"/><LinePlanningInfo sku={item.sku} lineKey={item.line_key} served={served>=item.quantity} part="note"/></div>})}</div></LinePlanningProvider></div></details>)}{!orders.length&&<div className="ops-empty"><span>✓</span><h2>No hay pedidos WEB</h2><p>No existen pedidos WEB para las fechas y el estado seleccionados.</p></div>}</div></>
}

function Operations({orders,onRefresh}:{orders:Order[];onRefresh:(mode:OperationsView,from?:string,to?:string,state?:string,delegation?:string)=>Promise<void>}) {
  const [origin,setOrigin]=useState<OrderOriginFilter>("ALL");
  const [webDelegation,setWebDelegation]=useState("TODAS");
  const [webStores,setWebStores]=useState<Store[]>([]);
  useEffect(()=>{api<Store[]>("/api/v1/store/orders/delegations").then(setWebStores).catch(()=>{})},[]);
  const [boardView,setBoardView]=useState<OperationsView>("active_kardex");
  const [orderSearch,setOrderSearch]=useState("");
  const [attendedSort,setAttendedSort]=useState<"number"|"duration">("number");
  const [attendedAscending,setAttendedAscending]=useState(false);
  const toggleAttendedSort=(key:"number"|"duration")=>{if(key===attendedSort)setAttendedAscending(value=>!value);else{setAttendedSort(key);setAttendedAscending(false)}};
  const [dateFrom,setDateFrom]=useState(()=>madridDate(new Date()));
  const [dateTo,setDateTo]=useState(()=>madridDate(new Date()));
  const [webState,setWebState]=useState("TODOS");
  const [now,setNow]=useState(Date.now());
  const [updating,setUpdating]=useState(false);
  const [refreshError,setRefreshError]=useState("");
  const updateBoard=async()=>{
    if(updating)return;
    setUpdating(true);setRefreshError("");
    try{await onRefresh(boardView,dateFrom,dateTo,webState,webDelegation);setNow(Date.now())}
    catch(e){setRefreshError((e as Error).message||"No se pudieron actualizar los datos. Inténtalo de nuevo.")}
    finally{setUpdating(false)}
  };
  useEffect(()=>{const timer=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(timer)},[]);
  useEffect(()=>{if(boardView==="attended"||boardView==="web")return;const timer=window.setInterval(()=>{setNow(Date.now());onRefresh(boardView).catch(()=>{})},10000);return()=>window.clearInterval(timer)},[onRefresh,boardView]);
  const attentionDuration=(order:Order)=>{
    if(order.dispatch_date_error)return null;
    const start=new Date(order.fecha_registro_exit||order.created_at).getTime();
    const end=order.closed_at?new Date(order.closed_at).getTime():now;
    return Number.isFinite(start)&&Number.isFinite(end)&&end>=start?end-start:null;
  };
  const sorted=orders.filter(order=>(boardView!=="web"||order.origen_pedido==="B2B")&&matchesOrderOrigin(order,origin)&&(!orderSearch.trim()||displayOrderNumber(order).toLowerCase().includes(orderSearch.trim().toLowerCase())||order.number.toLowerCase().includes(orderSearch.trim().toLowerCase())||(order.nro_pedido_exit||"").toLowerCase().includes(orderSearch.trim().toLowerCase()))).sort((a,b)=>{
    const numberCompare=orderNumberValue(a)-orderNumberValue(b)||a.number.localeCompare(b.number,"es");
    if(boardView!=="attended")return -numberCompare;
    if(attendedSort==="number")return attendedAscending?numberCompare:-numberCompare;
    const first=attentionDuration(a),second=attentionDuration(b);
    if(first===null||second===null)return first===second?-numberCompare:first===null?1:-1;
    const comparison=first-second;
    return (attendedAscending?comparison:-comparison)||-numberCompare;
  });
  const age=(created:string)=>{const mins=Math.max(0,Math.floor((now-new Date(created).getTime())/60000));return mins<60?`${mins} min`:mins<1440?`${Math.floor(mins/60)} h ${mins%60} min`:`${Math.floor(mins/1440)} d`};
  const elapsed=(seconds:number)=>{const total=Math.max(0,Math.floor(seconds));const hours=Math.floor(total/3600);const minutes=Math.floor(total%3600/60);const secs=total%60;return hours>0?`${hours}h ${String(minutes).padStart(2,"0")}m ${String(secs).padStart(2,"0")}s`:`${minutes}m ${String(secs).padStart(2,"0")}s`};
  const selectView=(mode:OperationsView)=>{setBoardView(mode);setOrigin("ALL");if(mode==="web"||mode==="attended"){const start=new Date();start.setDate(start.getDate()-30);const from=madridDate(start);setDateFrom(from);setWebState("TODOS");setRefreshError("");onRefresh(mode,from,dateTo,"TODOS",webDelegation).catch(e=>setRefreshError((e as Error).message));}else onRefresh(mode,dateFrom,dateTo,webState).catch(e=>setRefreshError((e as Error).message))};
  return <div className="page ops-page"><header className="ops-heading"><div className="ops-titlebar"><span>KARDEX</span><h1>{boardView==="web"?"Pedidos WEB":"Comandas de pedidos"}</h1></div><button className="ops-refresh" onClick={updateBoard} disabled={updating} aria-busy={updating}>{updating?"Actualizando…":"↻ Actualizar"}</button></header>{refreshError&&<p role="alert">{refreshError}</p>}<div className="ops-toolbar-row"><p className="ops-update-note">↻ Consulta directa a EXIT. Los activos se actualizan cada 10 segundos.</p><div className="ops-date-filters"><label>N.º pedido<input type="search" placeholder="Ej. 6006789" value={orderSearch} onChange={event=>setOrderSearch(event.target.value)} aria-label="Buscar pedido por número"/></label>{(boardView==="attended"||boardView==="web")&&<><label>Desde<input type="date" value={dateFrom} max={dateTo||undefined} onChange={event=>setDateFrom(event.target.value)}/></label><label>Hasta<input type="date" value={dateTo} min={dateFrom||undefined} onChange={event=>setDateTo(event.target.value)}/></label></>}{boardView==="web"&&<label>Delegación<select value={webDelegation} onChange={event=>setWebDelegation(event.target.value)}><option value="TODAS">Todas las delegaciones permitidas</option>{webStores.map(store=><option key={store.id} value={store.id}>{store.name}</option>)}</select></label>}{boardView==="web"&&<label>Estado<select value={webState} onChange={event=>setWebState(event.target.value)}><option value="BORRADOR">Borrador</option><option value="PENDIENTE">Pendiente</option><option value="BLOQUEADO">Bloqueado</option><option value="REGISTRADO">Registrado</option><option value="EN_PROCESO">En proceso</option><option value="EN_PREPARACION">En preparación</option><option value="ATENDIDO">Atendido</option><option value="ENTREGADO">Entregado</option><option value="FACTURADO">Facturado</option><option value="TODOS">Todos</option></select></label>}{boardView!=="web"&&<label>Origen<select value={origin} onChange={event=>setOrigin(event.target.value as OrderOriginFilter)}><option value="WEB">WEB</option><option value="ALL">Todos</option><option value="NON_WEB">No WEB</option></select></label>}{(boardView==="attended"||boardView==="web")&&<button onClick={updateBoard} disabled={updating}>{updating?"Consultando…":"Consultar"}</button>}</div>{boardView==="attended"&&<div className="ops-sort-controls" role="group" aria-label="Ordenar atendidos"><span>Ordenar:</span>{(["duration","number"] as const).map(key=><button key={key} aria-pressed={attendedSort===key} title={key==="duration"?"Tiempo desde registro EXIT hasta Atendido; si no está atendido, hasta ahora":"Número de pedido"} onClick={()=>toggleAttendedSort(key)}>{key==="duration"?"Tiempo de atención":"N.º pedido"} {attendedSort===key?(attendedAscending?"↑":"↓"):"↕"}</button>)}</div>}<nav className="ops-filters" aria-label="Tipo de pedidos"><button className={boardView==="active_kardex"?"active":""} onClick={()=>selectView("active_kardex")}>Activos Kardex {boardView==="active_kardex"&&<b>{orders.length}</b>}</button><button className={boardView==="attended"?"active":""} onClick={()=>selectView("attended")}>Atendidos {boardView==="attended"&&<b>{orders.length}</b>}</button><button className={boardView==="active_sga"?"active":""} onClick={()=>selectView("active_sga")}>Activos SGA {boardView==="active_sga"&&<b>{orders.length}</b>}</button><button className={boardView==="web"?"active":""} onClick={()=>selectView("web")}>Pedidos WEB {boardView==="web"&&<b>{sorted.length}</b>}</button></nav></div>{boardView==="web"?refreshError?<div className="ops-empty"><h2>No se pudieron consultar los pedidos WEB</h2><p>Pulsa Actualizar para volver a intentarlo.</p></div>:<OperatorWebOrders orders={sorted} onDelivered={()=>onRefresh(boardView,dateFrom,dateTo,webState,webDelegation)}/>:<div className="dispatch-list">{sorted.map(order=>{const registered=new Date(order.fecha_registro_exit||order.created_at);const closed=order.closed_at?new Date(order.closed_at):null;const references=new Set((order.items||[]).map(item=>item.sku)).size;const items=order.items||[];const kardexItems=items.filter(item=>item.fulfillment_zone==="KARDEX");const hasKardex=kardexItems.length>0;const kardexReferences=new Set(kardexItems.map(item=>item.sku)).size;const kardexSeconds=order.kardex_started_at?Math.max(0,((order.kardex_closed_at?new Date(order.kardex_closed_at).getTime():now)-new Date(order.kardex_started_at).getTime())/1000):null;const secondsPerReference=kardexSeconds!==null&&kardexReferences>0&&!order.kardex_date_error?kardexSeconds/kardexReferences:null;const kardexSpeed=secondsPerReference===null||!Number.isFinite(secondsPerReference)?"":secondsPerReference<=30?"fast":secondsPerReference<=45?"medium":"slow";const liveSeconds=Math.max(0,Math.floor(((closed?closed.getTime():now)-registered.getTime())/1000));const servedUnits=(item:OrderLine)=>item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));const fulfilledReferences=kardexItems.filter(item=>servedUnits(item)>=item.quantity).length;const progress=kardexItems.length?Math.round(fulfilledReferences/kardexItems.length*100):0;const fullyServed=kardexItems.length>0&&kardexItems.every(item=>servedUnits(item)>=item.quantity);const preparationLabel="Servido KDX";return <article className={`dispatch-order ${order.is_web_order?"is-web-order":"is-normal-order"}`} key={order.id}><header className="dispatch-header"><div className="dispatch-summary-top"><div className="dispatch-order-number"><small>N.º pedido</small><strong>{displayOrderNumber(order)}</strong></div><span className={`process-badge status-${fullyServed?"servido-kardex":"incompleto-kardex"}`}>◷ {preparationLabel}</span><div className="dispatch-progress"><b title={closed?"Tiempo total desde registro EXIT hasta Atendido":"Tiempo transcurrido desde registro EXIT"}>{order.dispatch_date_error||!Number.isFinite(liveSeconds)?"Revisar fechas":elapsed(liveSeconds)}</b><small className={`dispatch-clock-state ${closed?"closed":"live"}`}>{closed?"Tiempo cerrado":"◷ En curso"}</small><span title="Líneas servidas de Kardex"><small>KDX {fulfilledReferences}/{kardexItems.length}</small><i><em style={{width:`${progress}%`}}/></i><strong>{progress}%</strong></span></div></div><div className="dispatch-meta-grid"><div><small>Cliente</small><strong>{order.customer}</strong><span>Código: {order.customer_code||"—"}</span></div><div><small>Materiales</small><strong>{references} referencias</strong><span>{items.length} líneas</span></div><div><small>Usuario que generó el pedido</small><strong>{order.created_by||"—"}</strong></div><div><small>Estado</small><strong>{orderStateLabel(order.estado_registro_exit||"PENDIENTE")}</strong></div></div><div className="dispatch-timing-details"><div className="dispatch-timing-heading"><span className={`kardex-duration ${kardexSpeed}`} title={secondsPerReference!==null?`${secondsPerReference.toFixed(1)} segundos por referencia Kardex`:"Sin datos suficientes para calcular el tiempo por referencia"}>{order.kardex_started_at?`Tiempo Kardex: ${order.kardex_date_error?"Revisar fechas":elapsed(Math.max(0,Math.floor(((order.kardex_closed_at?new Date(order.kardex_closed_at).getTime():now)-new Date(order.kardex_started_at).getTime())/1000)))}${order.kardex_closed_at?"":" · en curso"}`:"Tiempo Kardex: —"}</span></div><ol className="dispatch-time-track" aria-label="Estados del pedido">{(["REGISTRADO","EN_PREPARACION","ATENDIDO","ENTREGADO"] as const).map((stage,index)=>{const stamp=order.operational_workflow?.find(step=>step.stage===stage)?.occurred_at||(stage==="REGISTRADO"?order.fecha_registro_exit:null);return <li key={stage} className={stamp?"complete":"pending"}><i>{index+1}</i><div><b>{({REGISTRADO:"Registrado",EN_PREPARACION:"En preparación",ATENDIDO:"Atendido",ENTREGADO:"Entregado"})[stage]}</b>{stamp?<time dateTime={stamp}>{new Date(stamp).toLocaleString("es-ES")}</time>:<span>Sin fecha</span>}</div></li>})}</ol></div></header><div className={`dispatch-note ${order.notes?"":"is-empty"}`}>{order.notes?<><b>Observaciones:</b> {order.notes}</>:<>&nbsp;</>}</div><CommandItems order={order}/></article>})}{!sorted.length&&<div className="ops-empty"><span>✓</span><h2>{orderSearch.trim()?"No se encontró ese pedido":boardView==="attended"?"No hay pedidos atendidos en estas fechas":"No hay pedidos pendientes"}</h2><p>{orderSearch.trim()?"La búsqueda considera la vista, las fechas y el origen seleccionados.":boardView==="attended"?"Amplía el rango de fechas para consultar pedidos anteriores.":"Consulta Atendidos para ver pedidos anteriores."}</p></div>}</div>}</div>
}

type OpeningDay={enabled?:boolean;morning_from:string;morning_to:string;afternoon_from:string;afternoon_to:string};
const emptyOpeningDay=():OpeningDay=>({enabled:false,morning_from:"",morning_to:"",afternoon_from:"",afternoon_to:""});
function PickupParameters(){
 const [tab,setTab]=useState("pickup");
 const [visited,setVisited]=useState<string[]>(["pickup"]);
 function selectTab(value:string){setTab(value);setVisited(old=>old.includes(value)?old:[...old,value])}
 return <section className="page settings-page"><h1>Parámetros</h1><p className="settings-intro">Selecciona la configuración que quieres consultar.</p><div className="settings-tabs" role="tablist" aria-label="Configuración">{[["pickup","Recogida y horarios"],["search","Buscador"],["synonyms","Sinónimos de producto"],["brands","Marcas"],["series","Series de pedidos"],["line-planning","Fechas por línea"],["appearance","Imagen de acceso"]].map(([id,label])=><button type="button" key={id} id={`settings-tab-${id}`} role="tab" aria-selected={tab===id} aria-controls={`settings-panel-${id}`} tabIndex={tab===id?0:-1} onClick={()=>selectTab(id)} onKeyDown={event=>{const ids=["pickup","search","synonyms","brands","series","line-planning","appearance"];let next=ids.indexOf(id);if(event.key==="ArrowRight")next=(next+1)%ids.length;else if(event.key==="ArrowLeft")next=(next+ids.length-1)%ids.length;else if(event.key==="Home")next=0;else if(event.key==="End")next=ids.length-1;else return;event.preventDefault();selectTab(ids[next]);document.getElementById(`settings-tab-${ids[next]}`)?.focus()}}>{label}</button>)}</div>{[["pickup",<PickupScheduleParameters key="pickup"/>],["search",<SearchParameters key="search"/>],["synonyms",<ProductTypeSynonyms key="synonyms"/>],["brands",<BrandParameters key="brands"/>],["series",<SalesOrderSeries key="series"/>],["line-planning",<LinePlanningParameters key="line-planning"/>],["appearance",<LoginAppearanceSettings key="appearance"/>]].map(([id,content])=><div key={String(id)} id={`settings-panel-${id}`} role="tabpanel" aria-labelledby={`settings-tab-${id}`} hidden={tab!==id}>{visited.includes(String(id))&&content}</div>)}</section>
}

function PickupScheduleParameters(){
 const [minutes,setMinutes]=useState(60),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
 const [stores,setStores]=useState<Store[]>([]),[schedules,setSchedules]=useState<Record<string,OpeningDay[]>>({});
 useEffect(()=>{Promise.all([api<{preparation_minutes:number;schedules:Record<string,OpeningDay[]>}>("/api/v1/pickup-settings"),api<Store[]>("/api/v1/stores")]).then(([data,rows])=>{setMinutes(data.preparation_minutes);setSchedules(data.schedules);setStores(rows);setLoaded(true)}).catch(e=>setMessage(e.message))},[]);
 function change(id:string,day:number,key:keyof OpeningDay,value:string|boolean){setSchedules(old=>{const days=(old[id]||Array.from({length:7},emptyOpeningDay)).map(row=>({...row}));if(key==="enabled")days[day].enabled=Boolean(value);else days[day][key]=String(value);return {...old,[id]:days}})}
 async function save(event:FormEvent){event.preventDefault();setBusy(true);try{await api("/api/v1/pickup-settings",{method:"PATCH",body:JSON.stringify({preparation_minutes:minutes,schedules})});setMessage("Parámetros de recogida guardados")}catch(e){setMessage((e as Error).message)}finally{setBusy(false)}}
 return <section><form className="section" onSubmit={save}><h2>Recogida inmediata</h2><label>Tiempo estimado de preparación (minutos)<input className="input" type="number" min="1" max="10080" required disabled={!loaded} value={minutes} onChange={e=>setMinutes(Number(e.target.value))}/></label><p>La preparación debe caber en un turno de hoy. Si el actual no alcanza, se utiliza el siguiente turno del mismo día. Horario de España peninsular. Marca Con atención en los días abiertos. Desmarcado indica cerrado; un turno sin horas tampoco tiene atención.</p><h2>Horarios de atención por sede</h2>{stores.map(store=><details key={store.id} className="cart-additional"><summary>{store.name}</summary><div className="visibility-table opening-hours-table"><table><thead><tr><th>Día</th><th>Con atención</th><th>Mañana desde</th><th>Mañana hasta</th><th>Tarde desde</th><th>Tarde hasta</th></tr></thead><tbody>{["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"].map((day,index)=><tr key={day}><th>{day}</th><td><input className="opening-day-check" type="checkbox" aria-label={`${store.name} ${day} con atención`} checked={schedules[store.id]?.[index]?.enabled??Object.values(schedules[store.id]?.[index]||{}).some(value=>typeof value==="string"&&value!=="")} onChange={e=>change(store.id,index,"enabled",e.target.checked)}/></td>{(["morning_from","morning_to","afternoon_from","afternoon_to"] as (Exclude<keyof OpeningDay,"enabled">)[]).map((key,column)=><td key={key}><input aria-label={`${store.name} ${day} ${["mañana desde","mañana hasta","tarde desde","tarde hasta"][column]}`} disabled={!(schedules[store.id]?.[index]?.enabled??Object.values(schedules[store.id]?.[index]||{}).some(value=>typeof value==="string"&&value!==""))} className="opening-hour-input" type="text" inputMode="text" placeholder="HH:MM" maxLength={5} pattern="([01][0-9]|2[0-3]):[0-5][0-9]" title="Escribe la hora en formato de 24 horas, por ejemplo 08:00 o 19:30. Vacío significa cerrado." value={schedules[store.id]?.[index]?.[key]||""} onChange={e=>change(store.id,index,key,e.target.value)}/></td>)}</tr>)}</tbody></table></div></details>)}<button className="primary" disabled={!loaded||busy}>Guardar</button>{message&&<p role="status">{message}</p>}</form></section>
}

function PickupEditor({order,onSaved}:{order:Order;onSaved:()=>Promise<void>}){
 const [editing,setEditing]=useState(false),[scheduled,setScheduled]=useState(!!order.pickup_date),[date,setDate]=useState(order.pickup_date||""),[busy,setBusy]=useState(false),[error,setError]=useState("");
 async function save(event:FormEvent){event.preventDefault();if(!scheduled&&!window.confirm("¿Atender este pedido como inmediato? Se aplicará tu decisión aunque el horario o el tiempo de preparación no permitan la recogida inmediata habitual."))return;setBusy(true);setError("");try{await api(`/api/v1/store/orders/${order.id}/pickup`,{method:"PATCH",body:JSON.stringify({pickup_date:scheduled?date:null})});setEditing(false);await onSaved()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 if(order.delivered_at||["ENTREGADO","FACTURADO"].includes(order.estado_registro_exit||""))return null;
 return <div className="pickup-editor">{!editing?<button className="secondary" onClick={()=>{setScheduled(!!order.pickup_date);setDate(order.pickup_date||"");setEditing(true)}}>Cambiar recogida</button>:<form onSubmit={save} className="access-actions"><select aria-label="Tipo de recogida" value={scheduled?"scheduled":"immediate"} onChange={e=>setScheduled(e.target.value==="scheduled")}><option value="immediate">Inmediata</option><option value="scheduled">Programada</option></select>{scheduled&&<input aria-label="Nueva fecha de recogida" type="date" required value={date} onChange={e=>setDate(e.target.value)}/>}<button className="primary" disabled={busy}>Guardar</button><button type="button" className="secondary" disabled={busy} onClick={()=>setEditing(false)}>Cancelar</button></form>}{error&&<p className="error" role="alert">{error}</p>}</div>
}
