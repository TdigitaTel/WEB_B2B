"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import CategoryUpload from "./CategoryUpload";

type View = "home" | "catalog" | "orders" | "documents" | "ops" | "category-upload" | "account";
type User = { id: string; name: string; email: string; role: string };
type AccountCustomer = { trade_name: string; legal_name: string; erp_id: string; tax_id: string; email: string; phone: string; billing_address: string; price_list: string; discount_pct: number };
type Store = { id: string; code: string; name: string; address: string; company_code: number; warehouse_code: string; warehouse_name: string };
type Stock = { store_code: string; store: string; available: number };
type Suggestion = { id: string; sku: string; name: string; price: number; area_id: number; family_id: number; subfamily_id: number; product_type_id: number };
type Product = { id: string; image_url: string; sku: string; name: string; brand: string; family: string; customer_price: number; list_price: number; price_with_tax: number; price_without_tax: number; tax_rate: number; total_available: number; stock: Stock[]; purchased_units?: number };
type CartItem = { id: number; product_id: string; sku: string; name: string; quantity: number; unit_price: number; line_total: number };
type OrderLine = { sku: string; description: string; quantity: number; served_quantity?: number|null; pending_quantity?: number|null; unit: string; unit_price: number; line_total: number; fulfillment_zone?: string };
type Cart = { items: CartItem[]; line_count: number; subtotal: number; tax_total: number; total: number; store: { id: string; name: string } | null };
type OrderDocument = { id: string; type: "ALBARAN"|"FACTURA"; number: string; total: number; created_at: string; status?: string; available: boolean };
type OrderHistoryEvent = { estado_registro_exit: string; source: string; note?: string|null; date_only?:boolean; created_at: string };
type WorkflowStep = { date_only?:boolean; etapa: "BORRADOR"|"PENDIENTE"|"EN_PROCESAMIENTO"|"PENDIENTE_RECOJO"|"ENTREGADO"|"FACTURADO"; completed_at: string|null };
type StockShortage = { sku:string; name:string; requested:number; available:number };
type Order = { operational_workflow?:{stage:string;occurred_at:string|null}[]; kardex_started_at?:string|null; kardex_closed_at?:string|null; kardex_date_error?:boolean; closed_at?:string|null; dispatch_seconds?:number|null; dispatch_date_error?:boolean; id: string; number: string; web_number?:string|null; exit_number?:string|null; local_order?:boolean; customer_code?: string|null; nro_pedido_exit?: string|null; fecha_registro_exit?: string|null; origen_pedido?: "B2B"|"EXIT"; estado_registro_exit?: string|null; workflow?: WorkflowStep[]; history_enabled?: boolean; history?: OrderHistoryEvent[]; stock_warning?:{store:string;items:StockShortage[]}|null; auxiliary_reference?:string|null; is_web_order?:boolean; store: string; customer: string; created_by: string; customer_reference?: string; job_name?: string; notes?: string; subtotal: number; tax_total: number; total: number; created_at: string; items?: OrderLine[]; documents?: OrderDocument[] };
type DocumentItem = { line:number; sku:string; description:string; unit:string; quantity:number; unit_price:number; discount_pct:number; net_amount:number; tax_rate:number; tax_amount:number; total:number; warehouse:string };
type DocumentRow = { id: string; number: string; total: number; subtotal?: number; tax_total?: number; created_at?: string; due_date?: string; status?: string; store_code?: string; order_number?: string; invoice_number?: string; document?: string; source?: string; items?:DocumentItem[] };
type ProductTypeNode = { id: number; code: string; name: string; count: number };
type SubfamilyNode = { id: number; code: string; name: string; count: number; product_types: ProductTypeNode[] };
type FamilyNode = { id: number; code: string; name: string; count: number; subfamilies: SubfamilyNode[] };
type AreaNode = { id: number; code: string; name: string; count: number; families: FamilyNode[] };
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
  const text = await response.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; }
  catch { throw new Error("El servicio no está disponible. Inténtalo de nuevo en unos segundos."); }
  if (!response.ok) throw new Error(data.detail || "No se pudo completar la operación");
  return data as T;
}

const money = (value: number) => value.toLocaleString("es-ES", { style: "currency", currency: "EUR" });
const units = (value: number) => value.toLocaleString("es-ES", { maximumFractionDigits: 3 });
const orderStateLabel = (value: string) => ({
  PENDIENTE_RECOJO: "PENDIENTE DE RECOJO",
  EN_PROCESAMIENTO: "EN PROCESAMIENTO",
}[value] || value.replaceAll("_", " "));
const visibleOrderStage = (estado?: string|null) => ({
  BORRADOR: "BORRADOR",
  PENDIENTE: "PENDIENTE",
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
  const [cartOpen, setCartOpen] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [refreshingOrders, setRefreshingOrders] = useState(false);
  const [deliveryNotes, setDeliveryNotes] = useState<DocumentRow[]>([]);
  const [invoices, setInvoices] = useState<DocumentRow[]>([]);
  const [opsOrders, setOpsOrders] = useState<Order[]>([]);
  const [kioskMode, setKioskMode] = useState(false);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [orderConfirmation, setOrderConfirmation] = useState<Order | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const isOperator = user?.role === "OPERADOR_TIENDA" || user?.role === "ADMIN";

  const loadAccount = useCallback(async () => {
    try {
      const account = await api<{ user: User; customer: typeof customer }>("/api/v1/account");
      setUser(account.user); setCustomer(account.customer);
      if (account.user.role === "OPERADOR_TIENDA" || account.user.role === "ADMIN") setView("ops");
    } catch { setUser(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadAccount(); }, [loadAccount]);

  useEffect(() => {
    const forced = new URLSearchParams(window.location.search).get("kiosk") === "1";
    const touchKiosk = window.matchMedia("(pointer: coarse)").matches && window.innerWidth >= 800;
    setKioskMode(forced || touchKiosk);
  }, []);

  const refreshCustomerData = useCallback(async () => {
    if (!user || isOperator) return;
    const [storeData, cartData, orderData, classificationData, favoriteData] = await Promise.all([
      api<Store[]>("/api/v1/stores"), api<Cart>("/api/v1/cart"), api<Order[]>("/api/v1/orders"),
      api<AreaNode[]>("/api/v1/catalog/classification"),
      api<{items:Product[];total:number}>("/api/v1/catalog/favorites?limit=8")
    ]);
    setStores(storeData); setCart(cartData); setOrders(orderData); setClassification(classificationData); setFavoriteProducts(favoriteData.items);
  }, [user, isOperator]);

  const refreshOrders = useCallback(async (from = madridDate(new Date()), to = madridDate(new Date()), state = "PENDIENTE") => {
    if (!user || isOperator) return;
    setRefreshingOrders(true);
    try { const params=new URLSearchParams({date_from:from,date_to:to,state});setOrders(await api<Order[]>(`/api/v1/orders?${params}`)); setError(""); }
    catch (e) { setError((e as Error).message); }
    finally { setRefreshingOrders(false); }
  }, [user, isOperator]);

  const refreshOperations = useCallback(async (mode: OperationsView = "active_kardex", from = "", to = "", state = "PENDIENTE") => {
    const params = new URLSearchParams({ view: mode });
    if ((mode === "attended"||mode === "web") && from) params.set("date_from", from);
    if ((mode === "attended"||mode === "web") && to) params.set("date_to", to);
    if (mode === "web") params.set("state",state);
    setOpsOrders(await api<Order[]>(`/api/v1/store/orders?${params}`));
    setError("");
  }, []);

  useEffect(() => { refreshCustomerData().catch(e => setError(e.message)); }, [refreshCustomerData]);

  useEffect(() => {
    if (view !== "orders" || !user || isOperator) return;
    refreshOrders();
  }, [view, user, isOperator, refreshOrders]);

  const searchProducts = useCallback(async (text = query, filters = catalogFilters) => {
    if (!user || isOperator) return;
    const result = await api<{ items: Product[]; total: number }>(productsUrl(text, filters));
    setProducts(result.items); setTotalProducts(result.total); setCatalogPage(1);
  }, [query, catalogFilters, user, isOperator]);

  useEffect(() => {
    if (!user || isOperator) return;
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
    if (!user || isOperator || loadingMoreProducts || products.length >= totalProducts) return;
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
    if (!suggestionsEnabled || query.trim().length < 2 || isOperator) { setSuggestions([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => api<Suggestion[]>(`/api/v1/search/suggestions?q=${encodeURIComponent(query)}`).then(items => { if (!cancelled) setSuggestions(items); }).catch(() => { if (!cancelled) setSuggestions([]); }), 180);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, isOperator, suggestionsEnabled]);

  useEffect(() => {
    if (view === "documents" && user && !isOperator) Promise.all([api<DocumentRow[]>("/api/v1/delivery-notes"), api<DocumentRow[]>("/api/v1/invoices")]).then(([a, b]) => { setDeliveryNotes(a); setInvoices(b); });
    if (view === "ops" && isOperator) refreshOperations().catch(e => setError(e.message));
  }, [view, user, isOperator, refreshOperations]);

  async function login(email: string, password: string) {
    setError("");
    const result = await api<{ user: User }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setUser(result.user); setLoading(true); await loadAccount();
  }

  async function logout() { await api("/api/v1/auth/logout", { method: "POST" }); location.reload(); }

  async function addProduct(productId: string, quantity = 1) {
    const updated = await api<Cart>("/api/v1/cart/items", { method: "POST", body: JSON.stringify({ product_id: productId, quantity }) });
    setCart(updated); setSuggestions([]);
  }

  async function updateCart(itemId: number, quantity: number) {
    if (quantity <= 0) return removeCart(itemId);
    setCart(await api<Cart>(`/api/v1/cart/items/${itemId}`, { method: "PATCH", body: JSON.stringify({ quantity }) }));
  }

  async function removeCart(itemId: number) { setCart(await api<Cart>(`/api/v1/cart/items/${itemId}`, { method: "DELETE" })); }

  async function repeatOrder(id: string) { setCart(await api<Cart>(`/api/v1/orders/${id}/repeat`, { method: "POST" })); setCartOpen(true); }

  async function checkout(storeId: string, jobName: string, reference: string, notes: string, draft: boolean) {
    const selectedStore=stores.find(store=>store.id===storeId);
    if(!selectedStore)throw new Error("Selecciona una delegación válida");
    const order = await api<Order>("/api/v1/orders", { method: "POST", body: JSON.stringify({ company_code: selectedStore.company_code, delegation_code: selectedStore.code, job_name: jobName || null, customer_reference: reference || null, notes: notes || null, draft }) });
    setCartOpen(false); setView("orders"); setOrderConfirmation(order); await refreshCustomerData();
  }

  async function submitDraft(id: string) {
    try {
      await api<Order>(`/api/v1/orders/${id}/submit`, { method: "POST" });
      setError(""); await refreshCustomerData();
    } catch (e) { setError((e as Error).message); }
  }

  async function deleteOrder(id: string) {
    if (!window.confirm("¿Eliminar este pedido? Esta acción no se puede deshacer.")) return;
    try {
      await api(`/api/v1/orders/${id}`, { method: "DELETE" });
      setError(""); await refreshCustomerData();
    } catch (e) { setError((e as Error).message); }
  }

  if (loading) return <div className="loading">Preparando el portal profesional…</div>;
  if (!user) return <Login onLogin={login} error={error} />;

  return <main className={`shell ${kioskMode?"kiosk-mode":""} ${keyboardOpen?"keyboard-open":""}`}>
    <header className="header">
      <div className="head">
        <button className="brand" onClick={() => setView(isOperator ? "ops" : "home")} aria-label="Inicio"><img src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa · 25 aniversario" /></button>
        {!isOperator&&<button className="menu-button" onClick={()=>setMenuOpen(true)}><span aria-hidden="true">☰</span> Menú</button>}
        {!isOperator && <div className="global-search">
          <form className="search-form" onSubmit={e => { e.preventDefault(); setView("catalog"); setSuggestionsEnabled(false); setSuggestions([]); searchProducts().catch(e=>setError(e.message)); }}>
            <select aria-label="Departamento" value={catalogFilters.areaId} onChange={e=>{setCatalogFilters({areaId:e.target.value,familyId:"",subfamilyId:"",productTypeId:""});setView("catalog")}}><option value="">Todos los departamentos</option>{classification.map(area=><option key={area.id} value={area.id}>{area.name}</option>)}</select>
            <input aria-label="Buscar productos" value={query} onChange={e => {setQuery(e.target.value);setSuggestionsEnabled(true);setCatalogFilters(emptyCatalogFilters);setView("catalog")}} onKeyDown={e=>{if(e.key==="Escape"){setSuggestionsEnabled(false);setSuggestions([])}}} placeholder="Busca por producto, referencia o medida" />
            {!!query && <button className="search-clear" aria-label="Limpiar búsqueda" type="button" onClick={()=>{setQuery("");setCatalogFilters(emptyCatalogFilters);setSuggestionsEnabled(false);setSuggestions([]);setView("catalog")}}>×</button>}
            {kioskMode&&<button className="keyboard-toggle" aria-label="Abrir teclado en pantalla" type="button" onClick={()=>setKeyboardOpen(value=>!value)}>⌨</button>}
            <button className="search-submit" aria-label="Buscar" type="submit">⌕</button>
          </form>
          {!!suggestions.length && <div className="suggestions" role="listbox" aria-label="Sugerencias de productos">{suggestions.map(p => <button className="suggestion" role="option" key={p.id} onClick={() => {setSuggestionsEnabled(false);setQuery(p.name);setCatalogFilters({areaId:String(p.area_id),familyId:String(p.family_id),subfamilyId:String(p.subfamily_id),productTypeId:String(p.product_type_id)});setSuggestions([]);setView("catalog")}}><span><b>{p.name}</b><br/><small>Código {p.sku}</small></span><span className="suggestion-side"><b>{money(p.price)}</b><small>Ver producto →</small></span></button>)}</div>}
        </div>}
        <button className="account-button" onClick={()=>setView("account")}><small>Hola, {user.name.split(" ")[0]}</small><b>Mi cuenta</b></button><button className="logout-button" onClick={logout}>Salir</button>
        {!isOperator && <button className="cart-button" onClick={() => setCartOpen(true)}>▤ <span>Mi carrito</span> {cart?.line_count || 0}</button>}
      </div>
      <nav className="desktop-nav">{(isOperator ? [["ops","Operaciones"],["category-upload","Carga de categorías"]] : [["home","Inicio"],["catalog","Catálogo"],["orders","Mis pedidos"],["documents","Albaranes y facturas"],["account","Mi cuenta"]]).map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>
    </header>
    <div className="service-strip"><span>ÁREA PROFESIONAL · Compra a tu ritmo</span><span>{stores.length} delegaciones · Recogida en tienda</span></div>{error && <div className="page error" role="alert">{error}</div>}
    {view === "home" && <Home customer={customer} orders={orders} products={favoriteProducts} classification={classification} onNavigate={setView} onSelectArea={areaId=>{setCatalogFilters({areaId:String(areaId),familyId:"",subfamilyId:"",productTypeId:""});setView("catalog")}} onAdd={addProduct} />}
    {view === "catalog" && <Catalog products={products} total={totalProducts} classification={classification} filters={catalogFilters} setFilters={setCatalogFilters} onAdd={addProduct} onLoadMore={loadMoreProducts} loadingMore={loadingMoreProducts} />}
    {view === "orders" && <Orders orders={orders} refreshing={refreshingOrders} onRefresh={refreshOrders} onRepeat={repeatOrder} onSubmitDraft={submitDraft} onDelete={deleteOrder} />}
    {view === "documents" && <Documents notes={deliveryNotes} invoices={invoices} />}
    {view === "account" && <Account user={user} customer={customer} />}
    {view === "ops" && <Operations orders={opsOrders} onRefresh={refreshOperations} />}
    {view === "category-upload" && isOperator && <CategoryUpload />}
    {!isOperator && <nav className="mobile-nav">{[["home","Inicio"],["catalog","Buscar"],["orders","Pedidos"],["account","Cuenta"]].map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>}
    {cartOpen && cart && <CartDrawer cart={cart} stores={stores} onClose={() => setCartOpen(false)} onUpdate={updateCart} onRemove={removeCart} onCheckout={checkout} />}
    {orderConfirmation && <OrderConfirmation order={orderConfirmation} onClose={()=>setOrderConfirmation(null)} onViewOrders={()=>{setOrderConfirmation(null);setView("orders")}} />}
    {menuOpen&&!isOperator&&<CatalogMenu classification={classification} onClose={()=>setMenuOpen(false)} onSelect={filters=>{setCatalogFilters(filters);setMenuOpen(false);setView("catalog")}} />}
    {kioskMode&&keyboardOpen&&<KioskKeyboard onKey={key=>{if(key==="BACKSPACE")setQuery(value=>Array.from(value).slice(0,-1).join(""));else if(key==="CLEAR")setQuery("");else if(key==="SPACE")setQuery(value=>value+" ");else setQuery(value=>value+key);setSuggestionsEnabled(true);setCatalogFilters(emptyCatalogFilters);setView("catalog")}} onSearch={()=>{setKeyboardOpen(false);setSuggestionsEnabled(false);setSuggestions([]);searchProducts().catch(e=>setError(e.message))}} onClose={()=>setKeyboardOpen(false)}/>}
  </main>;
}

function KioskKeyboard({onKey,onSearch,onClose}:{onKey:(key:string)=>void;onSearch:()=>void;onClose:()=>void}) { const rows=[["1","2","3","4","5","6","7","8","9","0","/",'"'],["Q","W","E","R","T","Y","U","I","O","P"],["A","S","D","F","G","H","J","K","L","Ñ"],["Z","X","C","V","B","N","M","-","."]]; return <aside className="kiosk-keyboard" aria-label="Teclado en pantalla"><div className="keyboard-head"><b>Teclado en pantalla</b><button onClick={onClose} aria-label="Cerrar teclado">×</button></div>{rows.map((row,index)=><div className="keyboard-row" key={index}>{row.map(key=><button key={key} onClick={()=>onKey(key)}>{key}</button>)}</div>)}<div className="keyboard-row keyboard-actions"><button onClick={()=>onKey("CLEAR")}>Limpiar</button><button className="space-key" onClick={()=>onKey("SPACE")}>Espacio</button><button onClick={()=>onKey("BACKSPACE")}>⌫ Borrar</button><button className="keyboard-search" onClick={onSearch}>Buscar</button></div></aside> }

function CatalogMenu({classification,onClose,onSelect}:{classification:AreaNode[];onClose:()=>void;onSelect:(filters:CatalogFilters)=>void}) { const [areaId,setAreaId]=useState(String(classification[0]?.id||"")); const area=classification.find(item=>String(item.id)===areaId); return <div className="menu-overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="mega-menu" role="dialog" aria-modal="true" aria-label="Categorías del catálogo"><div className="mega-menu-head"><div><span className="eyebrow">CATÁLOGO PROFESIONAL</span><h2>¿Qué material necesitas?</h2></div><button aria-label="Cerrar menú" onClick={onClose}>×</button></div><div className="mega-menu-body"><nav className="mega-departments"><b>Departamentos</b>{classification.map(item=><button key={item.id} className={areaId===String(item.id)?"active":""} onMouseEnter={()=>setAreaId(String(item.id))} onClick={()=>setAreaId(String(item.id))}>{item.name}<span>›</span></button>)}</nav><div className="mega-content"><button className="mega-all" onClick={()=>onSelect({areaId:String(area?.id||""),familyId:"",subfamilyId:"",productTypeId:""})}>Ver todo en {area?.name||"el catálogo"} →</button><div className="mega-family-grid">{area?.families.map(family=><section key={family.id}><button className="mega-family" onClick={()=>onSelect({areaId:String(area.id),familyId:String(family.id),subfamilyId:"",productTypeId:""})}>{family.name}</button>{family.subfamilies.slice(0,6).map(subfamily=><button key={subfamily.id} onClick={()=>onSelect({areaId:String(area.id),familyId:String(family.id),subfamilyId:String(subfamily.id),productTypeId:""})}>{subfamily.name}</button>)}</section>)}</div></div></div></section></div> }

function Login({onLogin,error}:{onLogin:(email:string,password:string)=>Promise<void>;error:string}) {
  const [loginError,setLoginError]=useState(""); const [email,setEmail]=useState("pumaresdavid@gmail.com"); const [password,setPassword]=useState("123456"); const [busy,setBusy]=useState(false);
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);try{await onLogin(email,password)}catch(e){setLoginError((e as Error).message)}finally{setBusy(false)}}
  return <div className="login"><section className="login-brand"><img className="login-logo" src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa"/><h1>Material profesional.<br/>Pedido en segundos.</h1><p>Consulta tu precio, comprueba stock local y deja el pedido preparado en cualquiera de nuestras cinco delegaciones.</p></section><section className="login-panel"><form className="login-form" onSubmit={submit}><h2>Acceso profesional</h2><p className="small">Entra con la cuenta de tu empresa.</p><label className="label">Usuario o email</label><input className="input" value={email} onChange={e=>setEmail(e.target.value)}/><label className="label">Contraseña</label><input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)}/>{(error||loginError)&&<p className="error">{error||loginError}</p>}<button className="primary block" disabled={busy}>{busy?"Entrando…":"Iniciar sesión"}</button><div className="demo-access"><p>Accesos de ejemplo</p><button type="button" onClick={()=>{setEmail("pumaresdavid@gmail.com");setPassword("123456")}}><span><b>DAVID PUMARES FERNANDEZ</b><small>Cliente EXITERP 00004</small></span><strong>pumaresdavid@gmail.com<small>Contraseña: 123456</small></strong></button><button type="button" onClick={()=>{setEmail("operador@bermudez.test");setPassword("123456")}}><span><b>Operaciones</b><small>Comandas y preparación</small></span><strong>operador@bermudez.test<small>Contraseña: 123456</small></strong></button></div></form></section></div>
}

function Home({customer,orders,products,classification,onNavigate,onSelectArea,onAdd}:{customer:AccountCustomer|null;orders:Order[];products:Product[];classification:AreaNode[];onNavigate:(v:View)=>void;onSelectArea:(id:number)=>void;onAdd:(id:string)=>void}) {
  const active = orders.filter(o=>o.estado_registro_exit!=="FACTURADO");
  const [openStockId,setOpenStockId]=useState<string|null>(null);
  return <div className="page"><section className="hero"><div><span className="eyebrow">TU MOSTRADOR DIGITAL</span><h1>Todo lo que necesitas.<br/>Listo para tu próxima obra.</h1><p>Hola, {customer?.trade_name || "profesional"}. Encuentra tu material y recógelo en tienda.</p><button className="primary" onClick={()=>onNavigate("catalog")}>Explorar catálogo →</button></div><div className="hero-note"><span>01 / BUSCA</span><span>02 / AÑADE</span><span>03 / RECOGE</span><b>Menos esperas.<br/>Más tiempo en obra.</b></div></section>
  <section className="department-showcase"><div className="section-heading"><div><span className="eyebrow">COMPRA POR DEPARTAMENTO</span><h2>¿Qué necesitas para tu instalación?</h2></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver todos →</button></div><div className="department-rail">{classification.slice(0,10).map((area,index)=><button key={area.id} className={`department-card tone-${index%6}`} onClick={()=>onSelectArea(area.id)}><span className="department-symbol" aria-hidden="true">{area.name.slice(0,2)}</span><b>{area.name}</b><small>{area.count.toLocaleString("es-ES")} productos</small><em>Explorar →</em></button>)}</div></section>
  <div className="home-grid"><div><section className="shortcut-grid"><button onClick={()=>onNavigate("orders")}><span>↻</span><b>Pedidos anteriores</b><small>Consulta y duplica pedidos</small></button><button onClick={()=>onNavigate("documents")}><span>▤</span><b>Tus documentos</b><small>Facturas y albaranes a mano</small></button><button onClick={()=>onNavigate("orders")}><span>✓</span><b>Estado de pedidos</b><small>Sigue cada etapa y su fecha</small></button></section><section className="section panel"><div className="section-heading"><div><span className="eyebrow">LOS QUE MÁS UTILIZAS</span><h2>Materiales favoritos</h2><p className="small">Tus artículos más comprados, ordenados por unidades.</p></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver catálogo →</button></div><div className="products">{products.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd} stockOpen={openStockId===p.id} onStockToggle={open=>setOpenStockId(open?p.id:null)}/>)}</div>{!products.length&&<p className="small">Todavía no hay compras anteriores disponibles para mostrar.</p>}</section></div>
  <aside className="activity-panel panel"><div className="section-heading"><h2>Mis pedidos</h2><span className="count">{active.length}</span></div><p className="small">El estado de tus últimas compras.</p>{active.slice(0,3).map(o=><div className="compact-order" key={o.id}><b>{o.number}</b><span className="small">{o.store} · {o.job_name||"Sin obra"}</span><span className="status">{orderStateLabel(visibleOrderStage(o.estado_registro_exit))}</span></div>)}{!active.length&&<p className="small">No tienes pedidos activos.</p>}<button className="ghost block" onClick={()=>onNavigate("orders")}>Ver todos mis pedidos →</button><div className="store-note"><b>Cerca de tu próxima obra</b><p>Almeiras · A Coruña · Sanxenxo · Ferrol · Santiago</p></div></aside></div></div>;
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
  const sorted=[...products].sort((a,b)=>sort==="price-asc"?a.price_with_tax-b.price_with_tax:sort==="price-desc"?b.price_with_tax-a.price_with_tax:sort==="name"?a.name.localeCompare(b.name,"es"):0);
  const hasFilters=!!(filters.areaId||filters.familyId||filters.subfamilyId||filters.productTypeId);
  return <div className="page catalog-page"><div className="catalog-title"><div><span className="eyebrow">CATÁLOGO PROFESIONAL</span><h1>{type?.name||subfamily?.name||family?.name||area?.name||"Productos para tu instalación"}</h1><p>Encuentra material por departamento y afina el resultado con filtros.</p></div></div>{hasFilters&&<nav className="catalog-breadcrumb" aria-label="Ruta de categoría"><button onClick={()=>setFilters(emptyCatalogFilters)}>Catálogo</button><span>›</span>{area&&<><button onClick={()=>selectArea(area.id)}>{area.name}</button></>}{family&&<><span>›</span><button onClick={()=>selectFamily(area!.id,family.id)}>{family.name}</button></>}{subfamily&&<><span>›</span><button onClick={()=>selectSubfamily(area!.id,family!.id,subfamily.id)}>{subfamily.name}</button></>}{type&&<><span>›</span><b>{type.name}</b></>}</nav>}{hasFilters&&<div className="active-filter-bar"><span>Filtros aplicados</span>{area&&<button onClick={()=>setFilters(emptyCatalogFilters)}>{area.name} ×</button>}{family&&<button onClick={()=>selectArea(area!.id)}>{family.name} ×</button>}{subfamily&&<button onClick={()=>selectFamily(area!.id,family!.id)}>{subfamily.name} ×</button>}{type&&<button onClick={()=>selectSubfamily(area!.id,family!.id,subfamily!.id)}>{type.name} ×</button>}<button className="clear-all" onClick={()=>setFilters(emptyCatalogFilters)}>Limpiar todo</button></div>}<div className="catalog-toolbar"><button className="mobile-filter-button" onClick={()=>setFiltersOpen(true)}>☷ Filtrar</button><div><b>{total.toLocaleString("es-ES")} resultados</b><div className="small">Precio y disponibilidad actualizados</div></div><label className="sort-control">Ordenar por<select value={sort} onChange={e=>setSort(e.target.value)}><option value="relevance">Relevancia</option><option value="name">Nombre</option><option value="price-asc">Precio: menor a mayor</option><option value="price-desc">Precio: mayor a menor</option></select></label></div><div className="facet-layout"><aside className={`facet-panel ${filtersOpen?"open":""}`}><div className="facet-head"><div><b>Filtrar por</b><small>Selecciona una opción</small></div><button onClick={()=>setFiltersOpen(false)}>×</button></div><details className="facet-group" open><summary>Departamento</summary><div className="facet-options"><button className={!filters.areaId?"active":""} onClick={()=>setFilters(emptyCatalogFilters)}>Todos <span>{classification.reduce((sum,item)=>sum+item.count,0)}</span></button>{classification.map(item=><button key={item.id} className={filters.areaId===String(item.id)?"active":""} onClick={()=>selectArea(item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>{area&&<details className="facet-group" open><summary>Familia</summary><div className="facet-options">{area.families.map(item=><button key={item.id} className={filters.familyId===String(item.id)?"active":""} onClick={()=>selectFamily(area.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}{family&&<details className="facet-group" open><summary>Subfamilia</summary><div className="facet-options">{family.subfamilies.map(item=><button key={item.id} className={filters.subfamilyId===String(item.id)?"active":""} onClick={()=>selectSubfamily(area!.id,family.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}{subfamily&&<details className="facet-group" open><summary>Tipo de producto</summary><div className="facet-options">{subfamily.product_types.map(item=><button key={item.id} className={filters.productTypeId===String(item.id)?"active":""} onClick={()=>selectType(area!.id,family!.id,subfamily.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}<button className="primary facet-done" onClick={()=>setFiltersOpen(false)}>Ver {total.toLocaleString("es-ES")} productos</button></aside>{filtersOpen&&<button className="facet-backdrop" aria-label="Cerrar filtros" onClick={()=>setFiltersOpen(false)}/>}<section className="catalog-results"><div className="products">{sorted.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd} stockOpen={openStockId===p.id} onStockToggle={open=>setOpenStockId(open?p.id:null)}/>)}</div>{!products.length&&<div className="empty-state"><h2>No encontramos ese material</h2><p>Prueba otra referencia, menos palabras o limpia los filtros aplicados.</p></div>}<div ref={loadMoreRef} className="catalog-load-more" aria-live="polite">{loadingMore?"Cargando más productos…":hasMore?"Desplázate para ver más":`${products.length.toLocaleString("es-ES")} productos mostrados`}</div></section></div></div>
}

function ProductCard({product,onAdd,stockOpen=false,onStockToggle=()=>{}}:{product:Product;onAdd:(id:string,qty?:number)=>void;stockOpen?:boolean;onStockToggle?:(open:boolean)=>void}) { const [qty,setQty]=useState(1); const [imageFailed,setImageFailed]=useState(false); return <article className="product"><div className="product-image-wrap"><span className="product-code">Ref. {product.sku}</span><div className={`product-visual ${imageFailed?"image-missing":""}`}>{!imageFailed?<img src={product.image_url} alt={product.name} loading="lazy" onError={()=>setImageFailed(true)}/>:<><span aria-hidden="true">{product.family.slice(0,2).toUpperCase()}</span><small>{product.family}</small></>}</div></div><div className="product-body"><span className="family-name">{product.family}</span><h3>{product.name}</h3><span className="sku">{product.brand} · Código {product.sku}</span><div className="price-block"><span>Precio con IVA</span><div className="price">{money(product.price_with_tax)}</div><small>{money(product.price_without_tax)} sin IVA</small></div><details className="stock-popover" open={stockOpen}><summary className="stock" onClick={event=>{event.preventDefault();onStockToggle(!stockOpen)}} aria-label={`Stock total ${product.total_available} unidades. Abrir detalle por almacén`}><span className="availability-dot"/> {Math.max(0,Math.round(product.total_available))} uds. disponibles <span aria-hidden="true">ⓘ</span></summary><div className="stock-detail"><b>Disponibilidad por almacén</b><small className="stock-help">Pulsa de nuevo en el total para cerrar.</small>{product.stock.length?product.stock.map(item=><div className="stock-row" key={item.store_code}><span>{item.store}<small>Almacén {item.store_code}</small></span><strong>{item.available.toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</strong></div>):<p>Sin existencias en los almacenes incluidos.</p>}<div className="stock-note">No incluye los almacenes configurados como excluidos.</div></div></details><div className="product-actions"><label><span>Uds.</span><input className="qty" type="number" min="1" value={qty} onChange={e=>setQty(Math.max(1,Number(e.target.value)))}/></label><button className="secondary block" onClick={()=>onAdd(product.id,qty)}>Añadir al carrito</button></div></div></article> }

type OrderOriginFilter = "ALL" | "WEB" | "NON_WEB";
const isWebOrder=(order:Order)=>order.is_web_order===true||order.origen_pedido==="B2B"||String(order.auxiliary_reference||"").toUpperCase().replace(/\s/g,"").includes("PEDIDOGENERADOWEBB2B");
function OrderOriginMark({order}:{order:Order}) {const web=isWebOrder(order);return <span className={`order-origin-check ${web?"web":"normal"}`}><input type="checkbox" checked={web} readOnly tabIndex={-1} aria-label={web?"Generado por WEB":"No generado por WEB"}/><b>{web?"WEB":"No WEB"}</b></span>}
const matchesOrderOrigin=(order:Order,origin:OrderOriginFilter)=>origin==="ALL"||(origin==="WEB"?isWebOrder(order):!isWebOrder(order));

function Orders({orders,refreshing,onRefresh,onRepeat,onSubmitDraft,onDelete}:{orders:Order[];refreshing:boolean;onRefresh:(from?:string,to?:string,state?:string)=>void;onRepeat:(id:string)=>void;onSubmitDraft:(id:string)=>void;onDelete:(id:string)=>void}) {
  const [origin,setOrigin]=useState<OrderOriginFilter>("ALL");
  const visibleOrders=orders.filter(order=>matchesOrderOrigin(order,origin));
  const today=madridDate(new Date()); const [from,setFrom]=useState(today); const [to,setTo]=useState(today); const [state,setState]=useState("PENDIENTE"); const [showDocuments,setShowDocuments]=useState(false);
  const documents=visibleOrders.flatMap(o=>(o.documents||[]).map(d=>({...d,order:o.number}))); const bulkUrl=`/api/v1/documents/download?${new URLSearchParams({date_from:from,date_to:to})}`;
  const documentAction=(d:OrderDocument)=>d.available?<a className="doc-action" href={`/api/v1/documents/${d.type}/${d.id}/file`} target="_blank">Abrir</a>:<span className="status">Registrado</span>;
  return <div className="page orders-page"><div className="section-heading"><div><span className="eyebrow">GESTOR DE FLUJO</span><h1>Mis pedidos</h1><p className="small">Pedidos B2B y EXIT unificados, con prioridad para la información actual de EXIT.</p></div><div className="orders-heading-actions"><button className="ghost" disabled={refreshing} onClick={()=>onRefresh(from,to,state)}>{refreshing?"Actualizando…":"↻ Actualizar pedidos"}</button><button className="ghost" onClick={()=>setShowDocuments(!showDocuments)}>Documentación del resultado ({documents.length})</button></div></div>
  <section className="order-filters"><label>Desde<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>Hasta<input type="date" value={to} onChange={e=>setTo(e.target.value)}/></label><label>Estado<select value={state} onChange={e=>setState(e.target.value)}><option value="TODOS">Todos</option><option value="BORRADOR">Borrador</option><option value="PENDIENTE">Pendiente</option><option value="EN_PROCESAMIENTO">En procesamiento</option><option value="PENDIENTE_RECOJO">Pendiente de recojo</option><option value="ENTREGADO">Entregado</option><option value="FACTURADO">Facturado</option></select></label><label>Origen<select value={origin} onChange={e=>setOrigin(e.target.value as OrderOriginFilter)}><option value="WEB">WEB</option><option value="ALL">Todos</option><option value="NON_WEB">No WEB</option></select></label><button className="primary" disabled={refreshing} onClick={()=>onRefresh(from,to,state)}>Consultar</button><span>{visibleOrders.length} pedidos</span></section>
  {showDocuments&&<section className="bulk-documents panel"><div className="section-heading"><h2>Documentación del resultado</h2>{documents.some(d=>d.available)&&<a className="secondary doc-download" href={bulkUrl}>Descargar disponibles (.zip)</a>}</div>{documents.length?documents.map(d=><div className="document-line" key={`${d.type}-${d.id}`}><span><b>{d.type} {d.number}</b><small>Pedido {d.order} · {new Date(d.created_at).toLocaleDateString("es-ES")}</small></span><strong>{money(d.total)}</strong>{documentAction(d)}</div>):<p className="small">No hay documentos para los filtros seleccionados.</p>}</section>}
  <div className="orders-list">{visibleOrders.map(o=>{const isDraft=o.estado_registro_exit==="BORRADOR";const canDelete=!!o.local_order&&(isDraft||o.estado_registro_exit==="PENDIENTE")&&!o.nro_pedido_exit;return <details className="order-card" key={o.id}><summary><span className="order-identifiers"><span className="order-number-origin"><b>{o.exit_number||o.web_number||o.number}</b><OrderOriginMark order={o}/></span>{o.exit_number&&o.web_number&&<small>Pedido web: {o.web_number}</small>}<small>{new Date(o.created_at).toLocaleString("es-ES")} · {o.store}</small></span><span><b>{o.customer}</b><small>{o.created_by}</small></span><span className={`workflow-badge stage-${visibleOrderStage(o.estado_registro_exit)}`}>{orderStateLabel(visibleOrderStage(o.estado_registro_exit))}</span><strong>{money(o.total)}</strong><span className="order-expand">{isDraft&&o.local_order?<button type="button" className="draft-inline-action" onClick={event=>{event.preventDefault();event.stopPropagation();onSubmitDraft(o.id)}}>Convertir en pendiente</button>:"Ver detalle⌄"}</span></summary><div className="order-content"><div className="order-meta"><span><small>Obra</small><b>{o.job_name||"Sin obra"}</b></span><span><small>Referencia</small><b>{o.customer_reference||"—"}</b></span><span><small>Observaciones</small><b>{o.notes||"—"}</b></span><div className="order-actions">{o.local_order&&<button className="secondary" onClick={()=>onRepeat(o.id)}>Duplicar pedido</button>}{canDelete&&<button className="danger-button" onClick={()=>onDelete(o.id)}>Eliminar pedido</button>}</div></div><div className="workflow">{(o.workflow||[]).map((step,index)=><div className={`workflow-step ${step.completed_at?"complete":""}`} key={step.etapa}><span>{index+1}</span><b>{orderStateLabel(step.etapa)}</b><small>{step.completed_at?(step.date_only?new Date(step.completed_at).toLocaleDateString("es-ES"):new Date(step.completed_at).toLocaleString("es-ES")):"Pendiente"}</small></div>)}</div><div className="order-lines"><div className="order-lines-head"><span>Artículo</span><span>Pedida</span><span>Servida</span><span>Precio</span><span>Total</span></div>{(o.items||[]).map((item,index)=>{const served=item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));return <div className="order-line" key={`${o.id}-${item.sku}-${index}`}><span><b>{item.description}</b><small>Código {item.sku}</small></span><span><b>{units(item.quantity)}</b><small>{item.unit||"UD"}</small></span><span className={served>=item.quantity?"quantity-complete":"quantity-partial"}><b>{units(served)}</b><small>{item.unit||"UD"}</small></span><span>{money(item.unit_price)}</span><strong>{money(item.line_total)}</strong></div>})}{!(o.items||[]).length&&<p className="order-lines-empty">Este pedido todavía no tiene líneas disponibles.</p>}</div><OrderHistory order={o}/><div className="order-documents"><h3>Documentación</h3>{o.documents?.length?o.documents.map(d=><div className="document-line" key={d.id}><span><b>{d.type} {d.number}</b><small>{new Date(d.created_at).toLocaleString("es-ES")}</small></span><strong>{money(d.total)}</strong>{documentAction(d)}</div>):<p className="small">Este pedido todavía no tiene documentos asociados.</p>}</div></div></details>})}</div>{!visibleOrders.length&&<div className="empty-state"><h2>No hay pedidos</h2><p>Cambia el origen, las fechas o el estado seleccionado y pulsa Consultar.</p></div>}</div>
}

function OrderHistory({order}:{order:Order}) {
  if (!order.history_enabled) return null;
  const events=order.history||[];
  return <details className="order-history"><summary>Ver historial de estados</summary><div className="order-history-list">{events.length?events.slice().sort((a,b)=>new Date(b.created_at).getTime()-new Date(a.created_at).getTime()).map((event,index)=><div className="order-history-event" key={`${event.estado_registro_exit}-${event.created_at}-${index}`}><span/><div><b>{orderStateLabel(event.estado_registro_exit)}</b><small>{event.source}{event.note?` · ${event.note}`:""}</small></div><time>{event.date_only?new Date(event.created_at).toLocaleDateString("es-ES"):new Date(event.created_at).toLocaleString("es-ES")}</time></div>):<p>No existen cambios registrados.</p>}</div></details>;
}

function Documents({notes,invoices}:{notes:DocumentRow[];invoices:DocumentRow[]}) {
  const today=madridDate(new Date()); const previousMonth=new Date(); previousMonth.setMonth(previousMonth.getMonth()-1); const monthAgo=madridDate(previousMonth);
  const [tab,setTab]=useState<"ALBARAN"|"FACTURA">("ALBARAN"); const [noteFilters,setNoteFilters]=useState({number:"",from:monthAgo,to:today}); const [invoiceFilters,setInvoiceFilters]=useState({number:"",from:monthAgo,to:today});
  const [loadedNotes,setLoadedNotes]=useState(notes); const [loadedInvoices,setLoadedInvoices]=useState(invoices); const [loadingDocuments,setLoadingDocuments]=useState(false);
  useEffect(()=>setLoadedNotes(notes),[notes]); useEffect(()=>setLoadedInvoices(invoices),[invoices]);
  const filters=tab==="ALBARAN"?noteFilters:invoiceFilters; const setFilters=tab==="ALBARAN"?setNoteFilters:setInvoiceFilters; const {number,from,to}=filters;
  const rows=tab==="ALBARAN"?loadedNotes:loadedInvoices; const normalizedNumber=number.replace(/[~\/\\-]/g,"").toLowerCase(); const filtered=rows.filter(row=>{const rowDate=row.created_at?.slice(0,10)||"";const rowNumber=row.number.replace(/[~\/\\-]/g,"").toLowerCase();return(!normalizedNumber||rowNumber.includes(normalizedNumber))&&(!from||rowDate>=from)&&(!to||rowDate<=to)});
  const title=tab==="ALBARAN"?"Albaranes":"Facturas"; const kindPath=tab.toLowerCase(); const exportParams=new URLSearchParams({kind:tab,...number&&{q:number},...from&&{date_from:from},...to&&{date_to:to}});
  const consult=async(target=tab,number=(target==="ALBARAN"?noteFilters.number:invoiceFilters.number))=>{const current=target==="ALBARAN"?noteFilters:invoiceFilters;const params=new URLSearchParams({...number&&{document_number:number},...current.from&&{date_from:current.from},...current.to&&{date_to:current.to}});setLoadingDocuments(true);try{const result=await api<DocumentRow[]>(`/api/v1/${target==="ALBARAN"?"delivery-notes":"invoices"}?${params}`);if(target==="ALBARAN")setLoadedNotes(result);else setLoadedInvoices(result)}finally{setLoadingDocuments(false)}};
  const openInvoice=async(number:string)=>{const next={...invoiceFilters,number};setInvoiceFilters(next);setTab("FACTURA");await consult("FACTURA",number)};
  return <div className="page documents-page"><div className="section-heading documents-title"><div><span className="eyebrow">DOCUMENTACIÓN EXIT</span><h1>Albaranes y facturas</h1><p className="small">Consulta, descarga o imprime tus documentos comerciales.</p></div></div><div className="document-tabs" role="tablist"><button className={tab==="ALBARAN"?"active":""} onClick={()=>setTab("ALBARAN")}>Albaranes <span>{loadedNotes.length}</span></button><button className={tab==="FACTURA"?"active":""} onClick={()=>setTab("FACTURA")}>Facturas <span>{loadedInvoices.length}</span></button></div><section className="document-toolbar"><label>{tab==="ALBARAN"?"Número de albarán":"Número de factura"}<input value={filters.number} onChange={event=>setFilters({...filters,number:event.target.value})} placeholder={tab==="ALBARAN"?"Ej. 2026-AL-12345":"Ej. 2026-FR-12345"}/></label><label>Desde<input type="date" value={from} onChange={event=>setFilters({...filters,from:event.target.value})}/></label><label>Hasta<input type="date" value={to} onChange={event=>setFilters({...filters,to:event.target.value})}/></label><button className="primary document-consult" disabled={loadingDocuments} onClick={()=>consult()}>{loadingDocuments?"Consultando…":"Consultar"}</button><div className="document-toolbar-actions"><a className="secondary" href={`/api/v1/documents/export?${exportParams}`}>Descargar Excel</a><button className="ghost" onClick={()=>window.print()}>Imprimir listado</button></div></section><div className="document-list-heading"><div><h2>{title}</h2><span>{filtered.length} documentos</span></div><strong>{money(filtered.reduce((sum,row)=>sum+row.total,0))}</strong></div><div className="document-cards">{filtered.map(row=><details className={`document-card ${tab==="FACTURA"?"invoice-card":""}`} key={row.id}><summary><span className="document-main"><small>{tab}</small><b>{row.number}</b><em>{row.created_at?new Date(row.created_at).toLocaleDateString("es-ES"):"Sin fecha"}</em></span>{tab==="ALBARAN"&&<span><small>Estado</small><b className="document-status">{orderStateLabel(row.status||"REGISTRADO")}</b></span>}<span><small>{tab==="ALBARAN"?"Pedido":"Vencimiento"}</small><b>{tab==="ALBARAN"?(row.order_number||"—"):(row.due_date?new Date(row.due_date).toLocaleDateString("es-ES"):"—")}</b></span><strong>{money(row.total)}</strong><span className="document-expand">Ver detalle⌄</span></summary><div className="document-detail"><div><small>Delegación</small><b>{row.store_code||"—"}</b></div><div><small>Base imponible</small><b>{money(row.subtotal||0)}</b></div><div><small>IVA</small><b>{money(row.tax_total||0)}</b></div><div><small>Total</small><b>{money(row.total)}</b></div>{row.invoice_number&&<div><small>Factura relacionada</small><button className="invoice-link" onClick={()=>openInvoice(row.invoice_number!)}>{row.invoice_number}</button></div>}{row.document&&<div><small>Documento EXIT</small><b>{row.document}</b></div>}<a className="primary document-download" href={`/api/v1/documents/${tab}/${row.id}/file`}>Descargar PDF</a></div>{tab==="ALBARAN"&&<div className="delivery-items"><div className="delivery-items-head"><span>Artículo despachado</span><span>Almacén</span><span>Cantidad</span><span>Precio</span><span>Importe</span></div>{(row.items||[]).map(item=><div className="delivery-item" key={`${row.id}-${item.line}`}><span><b>{item.description||"Artículo sin descripción"}</b><small>Código {item.sku} · Línea {item.line}</small></span><span>{item.warehouse||"—"}</span><span><b>{units(item.quantity)}</b> {item.unit||"UD"}</span><span>{money(item.unit_price)}</span><strong>{money(item.net_amount)}</strong></div>)}{!(row.items||[]).length&&<p className="delivery-empty">El albarán no contiene líneas de material.</p>}</div>}</details>)}{!filtered.length&&<div className="empty-state"><h2>No hay {kindPath === "albaran" ? "albaranes" : "facturas"}</h2><p>Cambia el número o el rango de fechas y pulsa Consultar.</p></div>}</div></div>
}

function Account({user,customer}:{user:User;customer:AccountCustomer|null}) {
  const [currentPassword,setCurrentPassword]=useState(""); const [newPassword,setNewPassword]=useState(""); const [confirmation,setConfirmation]=useState("");
  const [message,setMessage]=useState(""); const [passwordError,setPasswordError]=useState(""); const [saving,setSaving]=useState(false);
  const submit=async(event:FormEvent)=>{event.preventDefault();setMessage("");setPasswordError("");if(newPassword!==confirmation){setPasswordError("Las contraseñas nuevas no coinciden");return}setSaving(true);try{await api("/api/v1/account/password",{method:"PATCH",body:JSON.stringify({current_password:currentPassword,new_password:newPassword})});setCurrentPassword("");setNewPassword("");setConfirmation("");setMessage("Contraseña actualizada correctamente")}catch(error){setPasswordError((error as Error).message)}finally{setSaving(false)}};
  return <div className="page"><h1>Mi cuenta</h1><div className="account-layout"><section className="section"><h2>{customer?.trade_name||customer?.legal_name||user.name}</h2><p>Razón social: <b>{customer?.legal_name||"—"}</b></p><p>Código cliente EXITERP: <b>{customer?.erp_id||"—"}</b></p><p>NIF/CIF: {customer?.tax_id||"—"}</p><p>Dirección de facturación: {customer?.billing_address||"—"}</p><p>Contacto ERP: {customer?.email||customer?.phone||"—"}</p><p>Usuario de acceso: <b>{user.email}</b></p><small className="account-source">Los datos comerciales se consultan directamente en EXIT.</small></section><form className="section password-form" onSubmit={submit}><h2>Cambiar contraseña</h2><p className="small">La contraseña se guarda cifrada en la base de datos de la web.</p><label>Contraseña actual<input type="password" autoComplete="current-password" value={currentPassword} onChange={event=>setCurrentPassword(event.target.value)} required/></label><label>Nueva contraseña<input type="password" autoComplete="new-password" minLength={6} value={newPassword} onChange={event=>setNewPassword(event.target.value)} required/></label><label>Repetir nueva contraseña<input type="password" autoComplete="new-password" minLength={6} value={confirmation} onChange={event=>setConfirmation(event.target.value)} required/></label>{passwordError&&<div className="form-error">{passwordError}</div>}{message&&<div className="form-success">{message}</div>}<button className="primary" disabled={saving}>{saving?"Guardando…":"Actualizar contraseña"}</button></form></div></div>
}

function CartDrawer({cart,stores,onClose,onUpdate,onRemove,onCheckout}:{cart:Cart;stores:Store[];onClose:()=>void;onUpdate:(id:number,q:number)=>void;onRemove:(id:number)=>void;onCheckout:(s:string,j:string,r:string,n:string,d:boolean)=>void}) { const [store,setStore]=useState(cart.store?.id||stores[0]?.id||""); const [job,setJob]=useState(""); const [ref,setRef]=useState(""); const [notes,setNotes]=useState(""); const [draft,setDraft]=useState(false); return <><div className="drawer-back" onClick={onClose}/><aside className="drawer"><div className="drawer-head"><div><div className="small">PEDIDO EN PREPARACIÓN</div><h2>Tu pedido</h2></div><button className="close" onClick={onClose}>×</button></div><div className="cart-lines">{cart.items.map(item=><div className="cart-line" key={item.id}><div><b>{item.name}</b><div className="small">{item.sku} · {money(item.unit_price)} por unidad</div><strong className="cart-line-total">{money(item.line_total)}</strong></div><input aria-label={`Cantidad de ${item.name}`} type="number" min="1" value={item.quantity} onChange={e=>onUpdate(item.id,Number(e.target.value))}/><button className="ghost" aria-label={`Eliminar ${item.name}`} onClick={()=>onRemove(item.id)}>×</button></div>)}</div><div className="cart-totals"><div><span>Subtotal sin IVA</span><strong>{money(cart.subtotal)}</strong></div><div><span>IVA</span><strong>{money(cart.tax_total)}</strong></div><div className="cart-grand-total"><span>Total con IVA</span><strong>{money(cart.total)}</strong></div></div><label className="label">Recoger en</label><select className="select" value={store} onChange={e=>setStore(e.target.value)}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select><label className="label">Obra</label><input className="input" value={job} onChange={e=>setJob(e.target.value)} placeholder="Reforma Hotel Coruña"/><label className="label">Referencia cliente</label><input className="input" value={ref} onChange={e=>setRef(e.target.value)} placeholder="OBRA-324"/><label className="label">Observaciones</label><textarea className="textarea" rows={3} value={notes} onChange={e=>setNotes(e.target.value)}/><label className="draft-check"><input type="checkbox" checked={draft} onChange={e=>setDraft(e.target.checked)}/><span><b>Guardar como borrador</b><small>Podrás revisarlo y enviarlo después desde Mis pedidos.</small></span></label><button className="primary block" disabled={!cart.items.length||!store} onClick={()=>onCheckout(store,job,ref,notes,draft)}>{draft?"Guardar borrador":"Enviar pedido a tienda"}</button></aside></> }

function OrderConfirmation({order,onClose,onViewOrders}:{order:Order;onClose:()=>void;onViewOrders:()=>void}) {
  const draft=order.estado_registro_exit==="BORRADOR"; const warning=order.stock_warning;
  return <div className="confirmation-back" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="order-confirmation" role="dialog" aria-modal="true" aria-labelledby="confirmation-title"><button className="confirmation-close" aria-label="Cerrar" onClick={onClose}>×</button><div className="confirmation-icon" aria-hidden="true">✓</div><span className="eyebrow">{draft?"BORRADOR GUARDADO":"PEDIDO REGISTRADO"}</span><h2 id="confirmation-title">{draft?"Borrador guardado":"¡Pedido recibido!"}</h2><p>{draft?"El pedido todavía no se ha enviado a la tienda. Puedes revisarlo y enviarlo desde Mis pedidos.":<>Hemos enviado tu solicitud a <b>{order.store}</b>. Podrás seguir cada paso desde Mis pedidos.</>}</p>{warning&&<div className="confirmation-stock-warning"><b>Stock insuficiente en {warning.store}</b><p>El pedido se ha registrado, pero estos materiales podrían no estar disponibles para recoger el mismo día. Revisaremos si pueden atenderse desde otras delegaciones.</p>{warning.items.map(item=><span key={item.sku}><strong>{item.sku}</strong> {item.name}<small>Pedido: {units(item.requested)} · Disponible: {units(item.available)}</small></span>)}</div>}<div className="confirmation-number"><small>Número de pedido</small><strong>{order.number}</strong></div><div className="confirmation-summary"><span><small>Artículos</small><b>{order.items?.length||0}</b></span><span><small>Total con IVA</small><b>{money(order.total)}</b></span><span><small>Estado</small><b>{draft?"Borrador":"Registrado"}</b></span></div><div className="confirmation-next"><b>{draft?"Siguiente paso":"¿Qué ocurre ahora?"}</b><span>{draft?"Pulsa “Quitar borrador y enviar” cuando el pedido esté listo.":"La tienda revisará el pedido y cambiará su estado cuando entre en preparación."}</span></div><div className="confirmation-actions"><button className="ghost" onClick={onClose}>Seguir comprando</button><button className="primary" onClick={onViewOrders}>Ver mis pedidos</button></div></section></div>
}

function displayOrderNumber(order:Order) { return order.nro_pedido_exit?.split("/").pop()||order.number.replace(/^EXIT-[^-]*-[^-]*-/,""); }
function orderNumberValue(order:Order) { const value=displayOrderNumber(order); const numeric=Number(value.replace(/\D/g,"")); return Number.isFinite(numeric)?numeric:0; }

function CommandItems({order}:{order:Order}) {
  const [showSga,setShowSga]=useState(false);
  const servedQuantity=(item:OrderLine)=>item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));
  const pending=(item:OrderLine)=>Math.max(0,item.quantity-servedQuantity(item));
  const uniqueCount=(items:OrderLine[])=>new Set(items.map(item=>item.sku)).size;
  const renderItems=(items:OrderLine[])=><>{items.map(item=>{const served=servedQuantity(item)>=item.quantity;return <div className={`dispatch-line ${served?"is-served":""}`} key={`${order.id}-${item.fulfillment_zone}-${item.sku}`}><b>{item.sku}</b><span>{item.description}</span><strong>{served?<em>SERVIDO</em>:<><em>PENDIENTE</em><small>{pending(item).toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</small></>}</strong></div>})}{!items.length&&<p className="dispatch-empty">Sin materiales en esta zona</p>}</>;
  const kardex=(order.items||[]).filter(item=>item.fulfillment_zone==="KARDEX");
  const sga=(order.items||[]).filter(item=>item.fulfillment_zone!=="KARDEX");
  const zoneHeader=(label:string,items:OrderLine[])=><header><h3>{label}</h3><span>{uniqueCount(items)} referencias</span></header>;
  return <><div className="dispatch-zones"><section className="dispatch-zone zone-KARDEX">{zoneHeader("KARDEX",kardex)}<div className="dispatch-columns"><small>Código</small><small>Material</small><small>Estado</small></div><div className="dispatch-lines">{renderItems(kardex)}</div><footer>Tipos de material <b>{uniqueCount(kardex)}</b></footer></section><div className="dispatch-card-footer"><OrderOriginMark order={order}/><button className="sga-popup-trigger" disabled={!sga.length} onClick={()=>setShowSga(true)}>SGA</button></div></div>{showSga&&<div className="sga-modal-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setShowSga(false)}}><section className="sga-modal" role="dialog" aria-modal="true" aria-label={`Materiales SGA del pedido ${displayOrderNumber(order)}`}><header><div><small>Pedido {displayOrderNumber(order)}</small><h2>SGA</h2></div><button aria-label="Cerrar" onClick={()=>setShowSga(false)}>×</button></header><div className="dispatch-columns"><small>Código</small><small>Material</small><small>Estado</small></div><div className="dispatch-lines">{renderItems(sga)}</div><footer>{uniqueCount(sga)} referencias SGA</footer></section></div>}</>
}

function OperatorWebOrders({orders}:{orders:Order[]}) {
  return <div className="operator-web-list">{orders.map(order=><details className="operator-web-order" key={order.id}><summary><span className="order-identifiers"><b>{order.nro_pedido_exit||order.number}</b><small>{new Date(order.created_at).toLocaleString("es-ES")} · {order.store}</small></span><span><b>{order.customer}</b><small>Código {order.customer_code||"—"} · {order.created_by||"EXIT"}</small></span><span className={`workflow-badge stage-${visibleOrderStage(order.estado_registro_exit)}`}>{orderStateLabel(visibleOrderStage(order.estado_registro_exit))}</span><span><b>{(order.items||[]).length} líneas</b><small>{new Set((order.items||[]).map(item=>item.sku)).size} referencias</small></span><span className="order-expand">Ver detalle⌄</span></summary><div className="operator-web-detail"><div className="web-order-origin"><b>PEDIDO WEB</b><span>{order.auxiliary_reference}</span></div><div className="web-order-lines"><div className="web-order-lines-head"><span>Artículo</span><span>Zona</span><span>Pedida</span><span>Servida</span><span>Estado</span></div>{(order.items||[]).map((item,index)=>{const served=item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));return <div className="web-order-line" key={`${order.id}-${item.sku}-${index}`}><span><b>{item.description}</b><small>{item.sku}</small></span><span>{item.fulfillment_zone||"SGA"}</span><span>{units(item.quantity)}</span><span>{units(served)}</span><strong>{served>=item.quantity?"SERVIDO":"PENDIENTE"}</strong></div>})}</div></div></details>)}{!orders.length&&<div className="ops-empty"><span>✓</span><h2>No hay pedidos WEB</h2><p>No existen pedidos WEB para las fechas y el estado seleccionados.</p></div>}</div>
}

function Operations({orders,onRefresh}:{orders:Order[];onRefresh:(mode:OperationsView,from?:string,to?:string,state?:string)=>Promise<void>}) {
  const [origin,setOrigin]=useState<OrderOriginFilter>("ALL");
  const [boardView,setBoardView]=useState<OperationsView>("active_kardex");
  const [attendedSort,setAttendedSort]=useState<"number"|"duration">("number");
  const [attendedAscending,setAttendedAscending]=useState(false);
  const toggleAttendedSort=(key:"number"|"duration")=>{if(key===attendedSort)setAttendedAscending(value=>!value);else{setAttendedSort(key);setAttendedAscending(false)}};
  const [dateFrom,setDateFrom]=useState(()=>madridDate(new Date()));
  const [dateTo,setDateTo]=useState(()=>madridDate(new Date()));
  const [webState,setWebState]=useState("PENDIENTE");
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const timer=window.setInterval(()=>setNow(Date.now()),1000);return()=>window.clearInterval(timer)},[]);
  useEffect(()=>{if(boardView==="attended"||boardView==="web")return;const timer=window.setInterval(()=>{setNow(Date.now());onRefresh(boardView).catch(()=>{})},10000);return()=>window.clearInterval(timer)},[onRefresh,boardView]);
  const attentionDuration=(order:Order)=>{
    if(order.dispatch_date_error)return null;
    const start=new Date(order.fecha_registro_exit||order.created_at).getTime();
    const end=order.closed_at?new Date(order.closed_at).getTime():now;
    return Number.isFinite(start)&&Number.isFinite(end)&&end>=start?end-start:null;
  };
  const sorted=orders.filter(order=>matchesOrderOrigin(order,origin)).sort((a,b)=>{
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
  const selectView=(mode:OperationsView)=>{setBoardView(mode);setOrigin("ALL");if(mode==="web")setWebState("PENDIENTE");onRefresh(mode,dateFrom,dateTo,mode==="web"?"PENDIENTE":webState).catch(()=>{})};
  return <div className="page ops-page"><header className="ops-heading"><div className="ops-titlebar"><span>KARDEX</span><h1>Comandas de pedidos</h1></div><div className="ops-live"><span/> EN DIRECTO</div></header><div className="ops-toolbar-row"><p className="ops-update-note">↻ Consulta directa a EXIT. Los activos se actualizan cada 10 segundos.</p><div className="ops-date-filters">{(boardView==="attended"||boardView==="web")&&<><label>Desde<input type="date" value={dateFrom} max={dateTo||undefined} onChange={event=>setDateFrom(event.target.value)}/></label><label>Hasta<input type="date" value={dateTo} min={dateFrom||undefined} onChange={event=>setDateTo(event.target.value)}/></label></>}{boardView==="web"&&<label>Estado<select value={webState} onChange={event=>setWebState(event.target.value)}><option value="PENDIENTE">Pendiente</option><option value="EN_PROCESAMIENTO">En procesamiento</option><option value="PENDIENTE_RECOJO">Pendiente de recojo</option><option value="ENTREGADO">Entregado</option><option value="FACTURADO">Facturado</option><option value="TODOS">Todos</option></select></label>}{boardView!=="web"&&<label>Origen<select value={origin} onChange={event=>setOrigin(event.target.value as OrderOriginFilter)}><option value="WEB">WEB</option><option value="ALL">Todos</option><option value="NON_WEB">No WEB</option></select></label>}{(boardView==="attended"||boardView==="web")&&<button onClick={()=>onRefresh(boardView,dateFrom,dateTo,webState).catch(()=>{})}>Consultar</button>}</div>{boardView==="attended"&&<div className="ops-sort-controls" role="group" aria-label="Ordenar atendidos"><span>Ordenar:</span>{(["duration","number"] as const).map(key=><button key={key} aria-pressed={attendedSort===key} title={key==="duration"?"Tiempo desde registro EXIT hasta entrega; si no está entregado, hasta ahora":"Número de pedido"} onClick={()=>toggleAttendedSort(key)}>{key==="duration"?"Tiempo de atención":"N.º pedido"} {attendedSort===key?(attendedAscending?"↑":"↓"):"↕"}</button>)}</div>}<nav className="ops-filters" aria-label="Tipo de pedidos"><button className={boardView==="active_kardex"?"active":""} onClick={()=>selectView("active_kardex")}>Activos Kardex {boardView==="active_kardex"&&<b>{orders.length}</b>}</button><button className={boardView==="attended"?"active":""} onClick={()=>selectView("attended")}>Atendidos {boardView==="attended"&&<b>{orders.length}</b>}</button><button className={boardView==="active_sga"?"active":""} onClick={()=>selectView("active_sga")}>Activos SGA {boardView==="active_sga"&&<b>{orders.length}</b>}</button><button className={boardView==="web"?"active":""} onClick={()=>selectView("web")}>Pedidos WEB {boardView==="web"&&<b>{orders.length}</b>}</button></nav></div>{boardView==="web"?<OperatorWebOrders orders={sorted}/>:<div className="dispatch-list">{sorted.map(order=>{const registered=new Date(order.fecha_registro_exit||order.created_at);const closed=order.closed_at?new Date(order.closed_at):null;const references=new Set((order.items||[]).map(item=>item.sku)).size;const items=order.items||[];const kardexItems=items.filter(item=>item.fulfillment_zone==="KARDEX");const hasKardex=kardexItems.length>0;const kardexReferences=new Set(kardexItems.map(item=>item.sku)).size;const kardexSeconds=order.kardex_started_at?Math.max(0,((order.kardex_closed_at?new Date(order.kardex_closed_at).getTime():now)-new Date(order.kardex_started_at).getTime())/1000):null;const secondsPerReference=kardexSeconds!==null&&kardexReferences>0&&!order.kardex_date_error?kardexSeconds/kardexReferences:null;const kardexSpeed=secondsPerReference===null||!Number.isFinite(secondsPerReference)?"":secondsPerReference<=30?"fast":secondsPerReference<=45?"medium":"slow";const liveSeconds=Math.max(0,Math.floor(((closed?closed.getTime():now)-registered.getTime())/1000));const servedUnits=(item:OrderLine)=>item.served_quantity??Math.max(0,item.quantity-(item.pending_quantity??item.quantity));const servedLines=kardexItems.filter(item=>servedUnits(item)>=item.quantity).length;const progress=kardexItems.length?Math.round(servedLines/kardexItems.length*100):0;const fullyServed=items.length>0&&items.every(item=>servedUnits(item)>=item.quantity);const preparationStarted=items.some(item=>servedUnits(item)>0);const preparationLabel=fullyServed?"SERVIDO":preparationStarted?"EN PROCESO":"PENDIENTE";return <article className={`dispatch-order ${order.is_web_order?"is-web-order":"is-normal-order"}`} key={order.id}><header className="dispatch-header"><div className="dispatch-summary-top"><div className="dispatch-order-number"><small>N.º pedido</small><strong>{displayOrderNumber(order)}</strong></div><span className={`process-badge status-${preparationLabel.replace(" ","-").toLowerCase()}`}>◷ {preparationLabel}</span><div className="dispatch-progress"><b title={closed?"Tiempo total desde registro EXIT hasta entrega":"Tiempo transcurrido desde registro EXIT"}>{order.dispatch_date_error||!Number.isFinite(liveSeconds)?"Revisar fechas":elapsed(liveSeconds)}</b><small className={`dispatch-clock-state ${closed?"closed":"live"}`}>{closed?"Tiempo cerrado":"◷ En curso"}</small><span><small>{servedLines}/{kardexItems.length}</small><i><em style={{width:`${progress}%`}}/></i><strong>{progress}%</strong></span></div></div><div className="dispatch-meta-grid"><div><small>Cliente</small><strong>{order.customer}</strong><span>Código: {order.customer_code||"—"}</span></div><div><small>Materiales</small><strong>{references} referencias</strong><span>{items.length} líneas</span></div><div><small>Usuario que generó el pedido</small><strong>{order.created_by||"—"}</strong></div><div><small>Estado</small><strong>{orderStateLabel(order.estado_registro_exit||"PENDIENTE")}</strong></div></div><div className="dispatch-timing-details"><div className="dispatch-timing-heading"><span className={`kardex-duration ${kardexSpeed}`} title={secondsPerReference!==null?`${secondsPerReference.toFixed(1)} segundos por referencia Kardex`:"Sin datos suficientes para calcular el tiempo por referencia"}>{order.kardex_started_at?`Tiempo Kardex: ${order.kardex_date_error?"Revisar fechas":elapsed(Math.max(0,Math.floor(((order.kardex_closed_at?new Date(order.kardex_closed_at).getTime():now)-new Date(order.kardex_started_at).getTime())/1000)))}${order.kardex_closed_at?"":" · en curso"}`:"Tiempo Kardex: —"}</span></div><ol className="dispatch-time-track" aria-label="Estados del pedido">{(["REGISTRADO","EN_PREPARACION","ATENDIDO","ENTREGADO"] as const).map((stage,index)=>{const stamp=order.operational_workflow?.find(step=>step.stage===stage)?.occurred_at||(stage==="REGISTRADO"?order.fecha_registro_exit:null);return <li key={stage} className={stamp?"complete":"pending"}><i>{index+1}</i><div><b>{({REGISTRADO:"Registrado",EN_PREPARACION:"En preparación",ATENDIDO:"Atendido",ENTREGADO:"Entregado"})[stage]}</b>{stamp?<time dateTime={stamp}>{new Date(stamp).toLocaleString("es-ES")}</time>:<span>Sin fecha</span>}</div></li>})}</ol></div></header><div className={`dispatch-note ${order.notes?"":"is-empty"}`}>{order.notes?<><b>Observaciones:</b> {order.notes}</>:<>&nbsp;</>}</div><CommandItems order={order}/></article>})}{!sorted.length&&<div className="ops-empty"><span>✓</span><h2>No hay pedidos pendientes</h2><p>Los pedidos servidos se retiran automáticamente del tablero.</p></div>}</div>}</div>
}
