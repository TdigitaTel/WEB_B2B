"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type View = "home" | "catalog" | "orders" | "documents" | "ops" | "account";
type User = { id: string; name: string; email: string; role: string };
type AccountCustomer = { trade_name: string; legal_name: string; erp_id: string; tax_id: string; email: string; phone: string; billing_address: string; price_list: string; discount_pct: number };
type Store = { id: string; code: string; name: string; address: string };
type Stock = { store_code: string; store: string; available: number };
type Suggestion = { id: string; sku: string; name: string; price: number; area_id: number; family_id: number; subfamily_id: number; product_type_id: number };
type Product = { id: string; image_url: string; sku: string; name: string; brand: string; family: string; customer_price: number; list_price: number; price_with_tax: number; price_without_tax: number; tax_rate: number; total_available: number; stock: Stock[] };
type CartItem = { id: number; product_id: string; sku: string; name: string; quantity: number; unit_price: number; line_total: number };
type OrderLine = { sku: string; description: string; quantity: number; pending_quantity?: number|null; unit: string; unit_price: number; line_total: number; fulfillment_zone?: string };
type Cart = { items: CartItem[]; line_count: number; subtotal: number; tax_total: number; total: number; store: { id: string; name: string } | null };
type OrderDocument = { id: string; type: "ALBARAN"|"FACTURA"; number: string; total: number; created_at: string; status?: string; available: boolean };
type WorkflowStep = { status: "REGISTRADO"|"EN_PREPARACION"|"PREPARADO"|"FACTURADO"; completed_at: string|null };
type Order = { id: string; number: string; status: string; customer_code?: string|null; source_system?: string; authority_system?: string; exit_order_id?: string|null; exit_status?: string|null; kardex_completed_at?: string|null; kardex_duration_seconds?: number|null; sga_completed_at?: string|null; sga_duration_seconds?: number|null; workflow_status?: string; workflow?: WorkflowStep[]; store: string; customer: string; created_by: string; customer_reference?: string; job_name?: string; notes?: string; subtotal: number; tax_total: number; total: number; created_at: string; items?: OrderLine[]; documents?: OrderDocument[] };
type DocumentRow = { id: string; number: string; total: number; created_at?: string; due_date?: string; status?: string };
type ProductTypeNode = { id: number; code: string; name: string; count: number };
type SubfamilyNode = { id: number; code: string; name: string; count: number; product_types: ProductTypeNode[] };
type FamilyNode = { id: number; code: string; name: string; count: number; subfamilies: SubfamilyNode[] };
type AreaNode = { id: number; code: string; name: string; count: number; families: FamilyNode[] };
type CatalogFilters = { areaId: string; familyId: string; subfamilyId: string; productTypeId: string };

const emptyCatalogFilters: CatalogFilters = { areaId: "", familyId: "", subfamilyId: "", productTypeId: "" };

function productsUrl(text: string, filters: CatalogFilters) {
  const params = new URLSearchParams({ q: text, page_size: "48" });
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
const statusLabel = (value: string) => value.replaceAll("_", " ");

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
  const [totalProducts, setTotalProducts] = useState(0);
  const [classification, setClassification] = useState<AreaNode[]>([]);
  const [catalogFilters, setCatalogFilters] = useState<CatalogFilters>(emptyCatalogFilters);
  const [stores, setStores] = useState<Store[]>([]);
  const [cart, setCart] = useState<Cart | null>(null);
  const [cartOpen, setCartOpen] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
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
    const [storeData, cartData, orderData, classificationData] = await Promise.all([
      api<Store[]>("/api/v1/stores"), api<Cart>("/api/v1/cart"), api<Order[]>("/api/v1/orders"),
      api<AreaNode[]>("/api/v1/catalog/classification")
    ]);
    setStores(storeData); setCart(cartData); setOrders(orderData); setClassification(classificationData);
  }, [user, isOperator]);

  useEffect(() => { refreshCustomerData().catch(e => setError(e.message)); }, [refreshCustomerData]);

  const searchProducts = useCallback(async (text = query, filters = catalogFilters) => {
    if (!user || isOperator) return;
    const result = await api<{ items: Product[]; total: number }>(productsUrl(text, filters));
    setProducts(result.items); setTotalProducts(result.total);
  }, [query, catalogFilters, user, isOperator]);

  useEffect(() => {
    if (!user || isOperator) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const result = await api<{items:Product[];total:number}>(productsUrl(query, catalogFilters), {signal:controller.signal});
        setProducts(result.items); setTotalProducts(result.total); setError("");
      } catch(e) { if (!controller.signal.aborted) setError((e as Error).message); }
    }, 220);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, catalogFilters, user, isOperator]);

  useEffect(() => {
    if (!suggestionsEnabled || query.trim().length < 2 || isOperator) { setSuggestions([]); return; }
    let cancelled = false;
    const timer = window.setTimeout(() => api<Suggestion[]>(`/api/v1/search/suggestions?q=${encodeURIComponent(query)}`).then(items => { if (!cancelled) setSuggestions(items); }).catch(() => { if (!cancelled) setSuggestions([]); }), 180);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, isOperator, suggestionsEnabled]);

  useEffect(() => {
    if (view === "documents" && user && !isOperator) Promise.all([api<DocumentRow[]>("/api/v1/delivery-notes"), api<DocumentRow[]>("/api/v1/invoices")]).then(([a, b]) => { setDeliveryNotes(a); setInvoices(b); });
    if (view === "ops" && isOperator) api<Order[]>("/api/v1/store/orders").then(setOpsOrders).catch(e => setError(e.message));
  }, [view, user, isOperator]);

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

  async function checkout(storeId: string, jobName: string, reference: string, notes: string) {
    const order = await api<Order>("/api/v1/orders", { method: "POST", body: JSON.stringify({ store_id: storeId, job_name: jobName || null, customer_reference: reference || null, notes: notes || null }) });
    setCartOpen(false); setView("orders"); setOrderConfirmation(order); await refreshCustomerData();
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
      <nav className="desktop-nav">{(isOperator ? [["ops","Operaciones"]] : [["home","Inicio"],["catalog","Catálogo"],["orders","Mis pedidos"],["documents","Albaranes y facturas"],["account","Mi cuenta"]]).map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>
    </header>
    <div className="service-strip"><span>ÁREA PROFESIONAL · Compra a tu ritmo</span><span>5 delegaciones · Recogida en tienda</span></div>{error && <div className="page error" role="alert">{error}</div>}
    {view === "home" && <Home customer={customer} orders={orders} products={products.slice(0,8)} classification={classification} onNavigate={setView} onSelectArea={areaId=>{setCatalogFilters({areaId:String(areaId),familyId:"",subfamilyId:"",productTypeId:""});setView("catalog")}} onAdd={addProduct} />}
    {view === "catalog" && <Catalog products={products} total={totalProducts} classification={classification} filters={catalogFilters} setFilters={setCatalogFilters} onAdd={addProduct} />}
    {view === "orders" && <Orders orders={orders} onRepeat={repeatOrder} />}
    {view === "documents" && <Documents notes={deliveryNotes} invoices={invoices} />}
    {view === "account" && <Account user={user} customer={customer} />}
    {view === "ops" && <Operations orders={opsOrders} onRefresh={async()=>setOpsOrders(await api<Order[]>("/api/v1/store/orders"))} onTransition={async (id,status) => { await api(`/api/v1/store/orders/${id}/transitions`, {method:"POST",body:JSON.stringify({status})}); setOpsOrders(await api<Order[]>("/api/v1/store/orders")); }} />}
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
  const [loginError,setLoginError]=useState(""); const [email,setEmail]=useState("compras001@cliente.test"); const [password,setPassword]=useState("123456"); const [busy,setBusy]=useState(false);
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);try{await onLogin(email,password)}catch(e){setLoginError((e as Error).message)}finally{setBusy(false)}}
  return <div className="login"><section className="login-brand"><img className="login-logo" src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa"/><h1>Material profesional.<br/>Pedido en segundos.</h1><p>Consulta tu precio, comprueba stock local y deja el pedido preparado en cualquiera de nuestras cinco delegaciones.</p></section><section className="login-panel"><form className="login-form" onSubmit={submit}><h2>Acceso profesional</h2><p className="small">Entra con la cuenta de tu empresa.</p><label className="label">Usuario o email</label><input className="input" value={email} onChange={e=>setEmail(e.target.value)}/><label className="label">Contraseña</label><input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)}/>{(error||loginError)&&<p className="error">{error||loginError}</p>}<button className="primary block" disabled={busy}>{busy?"Entrando…":"Iniciar sesión"}</button><div className="demo-access"><p>Accesos de ejemplo</p><button type="button" onClick={()=>{setEmail("compras001@cliente.test");setPassword("123456")}}><span><b>Cliente profesional</b><small>Catálogo, carrito y pedidos</small></span><strong>compras001@cliente.test<small>Contraseña: 123456</small></strong></button><button type="button" onClick={()=>{setEmail("operador@bermudez.test");setPassword("123456")}}><span><b>Operaciones</b><small>Comandas y preparación</small></span><strong>operador@bermudez.test<small>Contraseña: 123456</small></strong></button></div></form></section></div>
}

function Home({customer,orders,products,classification,onNavigate,onSelectArea,onAdd}:{customer:AccountCustomer|null;orders:Order[];products:Product[];classification:AreaNode[];onNavigate:(v:View)=>void;onSelectArea:(id:number)=>void;onAdd:(id:string)=>void}) {
  const active = orders.filter(o=>o.status!=="ENTREGADO"&&o.status!=="CANCELADO");
  return <div className="page"><section className="hero"><div><span className="eyebrow">TU MOSTRADOR DIGITAL</span><h1>Todo lo que necesitas.<br/>Listo para tu próxima obra.</h1><p>Hola, {customer?.trade_name || "profesional"}. Encuentra tu material y recógelo en tienda.</p><button className="primary" onClick={()=>onNavigate("catalog")}>Explorar catálogo →</button></div><div className="hero-note"><span>01 / BUSCA</span><span>02 / AÑADE</span><span>03 / RECOGE</span><b>Menos esperas.<br/>Más tiempo en obra.</b></div></section>
  <section className="department-showcase"><div className="section-heading"><div><span className="eyebrow">COMPRA POR DEPARTAMENTO</span><h2>¿Qué necesitas para tu instalación?</h2></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver todos →</button></div><div className="department-rail">{classification.slice(0,10).map((area,index)=><button key={area.id} className={`department-card tone-${index%6}`} onClick={()=>onSelectArea(area.id)}><span className="department-symbol" aria-hidden="true">{area.name.slice(0,2)}</span><b>{area.name}</b><small>{area.count.toLocaleString("es-ES")} productos</small><em>Explorar →</em></button>)}</div></section>
  <div className="home-grid"><div><section className="shortcut-grid"><button onClick={()=>onNavigate("orders")}><span>↻</span><b>Pedidos anteriores</b><small>Consulta y duplica pedidos</small></button><button onClick={()=>onNavigate("documents")}><span>▤</span><b>Tus documentos</b><small>Facturas y albaranes a mano</small></button><button onClick={()=>onNavigate("orders")}><span>✓</span><b>Estado de pedidos</b><small>Sigue cada etapa y su fecha</small></button></section><section className="section panel"><div className="section-heading"><div><span className="eyebrow">MATERIAL PARA TU DÍA A DÍA</span><h2>Productos disponibles</h2></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver catálogo →</button></div><div className="products">{products.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd}/>)}</div></section></div>
  <aside className="activity-panel panel"><div className="section-heading"><h2>Mis pedidos</h2><span className="count">{active.length}</span></div><p className="small">El estado de tus últimas compras.</p>{active.slice(0,3).map(o=><div className="compact-order" key={o.id}><b>{o.number}</b><span className="small">{o.store} · {o.job_name||"Sin obra"}</span><span className="status">{statusLabel(o.status)}</span></div>)}{!active.length&&<p className="small">No tienes pedidos activos.</p>}<button className="ghost block" onClick={()=>onNavigate("orders")}>Ver todos mis pedidos →</button><div className="store-note"><b>Cerca de tu próxima obra</b><p>Almeiras · A Coruña · Sanxenxo · Ferrol · Santiago</p></div></aside></div></div>;
}

function Catalog({products,total,classification,filters,setFilters,onAdd}:{products:Product[];total:number;classification:AreaNode[];filters:CatalogFilters;setFilters:(f:CatalogFilters)=>void;onAdd:(id:string,qty?:number)=>void}) {
  const [filtersOpen,setFiltersOpen]=useState(false);
  const [openStockId,setOpenStockId]=useState<string|null>(null);
  const [sort,setSort]=useState("relevance");
  const selectArea=(id:number|string)=>setFilters({areaId:String(id),familyId:"",subfamilyId:"",productTypeId:""});
  const selectFamily=(areaId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(id),subfamilyId:"",productTypeId:""});
  const selectSubfamily=(areaId:number,familyId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(familyId),subfamilyId:String(id),productTypeId:""});
  const selectType=(areaId:number,familyId:number,subfamilyId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(familyId),subfamilyId:String(subfamilyId),productTypeId:String(id)});
  const area=classification.find(x=>String(x.id)===filters.areaId); const family=area?.families.find(x=>String(x.id)===filters.familyId); const subfamily=family?.subfamilies.find(x=>String(x.id)===filters.subfamilyId); const type=subfamily?.product_types.find(x=>String(x.id)===filters.productTypeId);
  const sorted=[...products].sort((a,b)=>sort==="price-asc"?a.price_with_tax-b.price_with_tax:sort==="price-desc"?b.price_with_tax-a.price_with_tax:sort==="name"?a.name.localeCompare(b.name,"es"):0);
  const hasFilters=!!(filters.areaId||filters.familyId||filters.subfamilyId||filters.productTypeId);
  return <div className="page catalog-page"><div className="catalog-title"><div><span className="eyebrow">CATÁLOGO PROFESIONAL</span><h1>{type?.name||subfamily?.name||family?.name||area?.name||"Productos para tu instalación"}</h1><p>Encuentra material por departamento y afina el resultado con filtros.</p></div><div className="catalog-count"><strong>{total.toLocaleString("es-ES")}</strong><span>referencias</span></div></div>{hasFilters&&<nav className="catalog-breadcrumb" aria-label="Ruta de categoría"><button onClick={()=>setFilters(emptyCatalogFilters)}>Catálogo</button><span>›</span>{area&&<><button onClick={()=>selectArea(area.id)}>{area.name}</button></>}{family&&<><span>›</span><button onClick={()=>selectFamily(area!.id,family.id)}>{family.name}</button></>}{subfamily&&<><span>›</span><button onClick={()=>selectSubfamily(area!.id,family!.id,subfamily.id)}>{subfamily.name}</button></>}{type&&<><span>›</span><b>{type.name}</b></>}</nav>}{hasFilters&&<div className="active-filter-bar"><span>Filtros aplicados</span>{area&&<button onClick={()=>setFilters(emptyCatalogFilters)}>{area.name} ×</button>}{family&&<button onClick={()=>selectArea(area!.id)}>{family.name} ×</button>}{subfamily&&<button onClick={()=>selectFamily(area!.id,family!.id)}>{subfamily.name} ×</button>}{type&&<button onClick={()=>selectSubfamily(area!.id,family!.id,subfamily!.id)}>{type.name} ×</button>}<button className="clear-all" onClick={()=>setFilters(emptyCatalogFilters)}>Limpiar todo</button></div>}<div className="catalog-toolbar"><button className="mobile-filter-button" onClick={()=>setFiltersOpen(true)}>☷ Filtrar</button><div><b>{total.toLocaleString("es-ES")} resultados</b><div className="small">Precio y disponibilidad actualizados</div></div><label className="sort-control">Ordenar por<select value={sort} onChange={e=>setSort(e.target.value)}><option value="relevance">Relevancia</option><option value="name">Nombre</option><option value="price-asc">Precio: menor a mayor</option><option value="price-desc">Precio: mayor a menor</option></select></label></div><div className="facet-layout"><aside className={`facet-panel ${filtersOpen?"open":""}`}><div className="facet-head"><div><b>Filtrar por</b><small>Selecciona una opción</small></div><button onClick={()=>setFiltersOpen(false)}>×</button></div><details className="facet-group" open><summary>Departamento</summary><div className="facet-options"><button className={!filters.areaId?"active":""} onClick={()=>setFilters(emptyCatalogFilters)}>Todos <span>{classification.reduce((sum,item)=>sum+item.count,0)}</span></button>{classification.map(item=><button key={item.id} className={filters.areaId===String(item.id)?"active":""} onClick={()=>selectArea(item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>{area&&<details className="facet-group" open><summary>Familia</summary><div className="facet-options">{area.families.map(item=><button key={item.id} className={filters.familyId===String(item.id)?"active":""} onClick={()=>selectFamily(area.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}{family&&<details className="facet-group" open><summary>Subfamilia</summary><div className="facet-options">{family.subfamilies.map(item=><button key={item.id} className={filters.subfamilyId===String(item.id)?"active":""} onClick={()=>selectSubfamily(area!.id,family.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}{subfamily&&<details className="facet-group" open><summary>Tipo de producto</summary><div className="facet-options">{subfamily.product_types.map(item=><button key={item.id} className={filters.productTypeId===String(item.id)?"active":""} onClick={()=>selectType(area!.id,family!.id,subfamily.id,item.id)}>{item.name}<span>{item.count}</span></button>)}</div></details>}<button className="primary facet-done" onClick={()=>setFiltersOpen(false)}>Ver {total.toLocaleString("es-ES")} productos</button></aside>{filtersOpen&&<button className="facet-backdrop" aria-label="Cerrar filtros" onClick={()=>setFiltersOpen(false)}/>}<section className="catalog-results"><div className="products">{sorted.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd} stockOpen={openStockId===p.id} onStockToggle={open=>setOpenStockId(open?p.id:null)}/>)}</div>{!products.length&&<div className="empty-state"><h2>No encontramos ese material</h2><p>Prueba otra referencia, menos palabras o limpia los filtros aplicados.</p></div>}</section></div></div>
}

function ProductCard({product,onAdd,stockOpen=false,onStockToggle=()=>{}}:{product:Product;onAdd:(id:string,qty?:number)=>void;stockOpen?:boolean;onStockToggle?:(open:boolean)=>void}) { const [qty,setQty]=useState(1); const [imageFailed,setImageFailed]=useState(false); return <article className="product"><div className="product-image-wrap"><span className="product-code">Ref. {product.sku}</span><div className={`product-visual ${imageFailed?"image-missing":""}`}>{!imageFailed?<img src={product.image_url} alt={product.name} loading="lazy" onError={()=>setImageFailed(true)}/>:<><span aria-hidden="true">{product.family.slice(0,2).toUpperCase()}</span><small>{product.family}</small></>}</div></div><div className="product-body"><span className="family-name">{product.family}</span><h3>{product.name}</h3><span className="sku">{product.brand} · Código {product.sku}</span><div className="price-block"><span>Precio con IVA</span><div className="price">{money(product.price_with_tax)}</div><small>{money(product.price_without_tax)} sin IVA</small></div><details className="stock-popover" open={stockOpen}><summary className="stock" onClick={event=>{event.preventDefault();onStockToggle(!stockOpen)}} aria-label={`Stock total ${product.total_available} unidades. Abrir detalle por almacén`}><span className="availability-dot"/> {Math.max(0,Math.round(product.total_available))} uds. disponibles <span aria-hidden="true">ⓘ</span></summary><div className="stock-detail"><b>Disponibilidad por almacén</b><small className="stock-help">Pulsa de nuevo en el total para cerrar.</small>{product.stock.length?product.stock.map(item=><div className="stock-row" key={item.store_code}><span>{item.store}<small>Almacén {item.store_code}</small></span><strong>{item.available.toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</strong></div>):<p>Sin existencias en los almacenes incluidos.</p>}<div className="stock-note">No incluye los almacenes configurados como excluidos.</div></div></details><div className="product-actions"><label><span>Uds.</span><input className="qty" type="number" min="1" value={qty} onChange={e=>setQty(Math.max(1,Number(e.target.value)))}/></label><button className="secondary block" onClick={()=>onAdd(product.id,qty)}>Añadir al carrito</button></div></div></article> }

function Orders({orders,onRepeat}:{orders:Order[];onRepeat:(id:string)=>void}) { const [from,setFrom]=useState(""); const [to,setTo]=useState(""); const [state,setState]=useState(""); const [showDocuments,setShowDocuments]=useState(false); const filtered=orders.filter(o=>(!from||o.created_at.slice(0,10)>=from)&&(!to||o.created_at.slice(0,10)<=to)&&(!state||o.workflow_status===state)); const documents=filtered.flatMap(o=>(o.documents||[]).map(d=>({...d,order:o.number}))); const bulkUrl=`/api/v1/documents/download?${new URLSearchParams({...from&&{date_from:from},...to&&{date_to:to}})}`; const documentAction=(d:OrderDocument)=>d.available?<a className="doc-action" href={`/api/v1/documents/${d.type}/${d.id}/file`} target="_blank">Abrir</a>:<span className="status">Registrado</span>; return <div className="page orders-page"><div className="section-heading"><div><span className="eyebrow">GESTOR DE FLUJO</span><h1>Mis pedidos</h1><p className="small">Pedidos de la cuenta conectada, con detalle, estado y documentación.</p></div><button className="ghost" onClick={()=>setShowDocuments(!showDocuments)}>Documentación del resultado ({documents.length})</button></div><section className="order-filters"><label>Desde<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>Hasta<input type="date" value={to} onChange={e=>setTo(e.target.value)}/></label><label>Estado<select value={state} onChange={e=>setState(e.target.value)}><option value="">Todos</option><option value="REGISTRADO">Registrado</option><option value="EN_PREPARACION">En preparación</option><option value="PREPARADO">Preparado</option><option value="FACTURADO">Facturado</option></select></label><span>{filtered.length} pedidos</span></section>{showDocuments&&<section className="bulk-documents panel"><div className="section-heading"><h2>Documentación filtrada</h2>{documents.some(d=>d.available)&&<a className="secondary doc-download" href={bulkUrl}>Descargar disponibles (.zip)</a>}</div>{documents.length?documents.map(d=><div className="document-line" key={`${d.type}-${d.id}`}><span><b>{d.type} {d.number}</b><small>Pedido {d.order} · {new Date(d.created_at).toLocaleDateString("es-ES")}</small></span><strong>{money(d.total)}</strong>{documentAction(d)}</div>):<p className="small">No hay documentos para los filtros seleccionados.</p>}</section>}<div className="orders-list">{filtered.map(o=><details className="order-card" key={o.id}><summary><span><b>{o.number}</b><small>{new Date(o.created_at).toLocaleString("es-ES")} · {o.store}</small></span><span><b>{o.customer}</b><small>{o.created_by}</small></span><span className={`workflow-badge stage-${o.workflow_status}`}>{statusLabel(o.workflow_status||o.status)}</span><strong>{money(o.total)}</strong><span className="order-expand">Ver detalle⌄</span></summary><div className="order-content"><div className="order-meta"><span><small>Obra</small><b>{o.job_name||"Sin obra"}</b></span><span><small>Referencia</small><b>{o.customer_reference||"—"}</b></span><span><small>Observaciones</small><b>{o.notes||"—"}</b></span><button className="secondary" onClick={()=>onRepeat(o.id)}>Duplicar pedido</button></div><div className="workflow">{(o.workflow||[]).map((step,index)=><div className={`workflow-step ${step.completed_at?"complete":""}`} key={step.status}><span>{index+1}</span><b>{statusLabel(step.status)}</b><small>{step.completed_at?new Date(step.completed_at).toLocaleString("es-ES"):"Pendiente"}</small></div>)}</div><div className="order-lines"><div className="order-lines-head"><span>Artículo</span><span>Cantidad</span><span>Precio</span><span>Total</span></div>{(o.items||[]).map(item=><div className="order-line" key={`${o.id}-${item.sku}`}><span><b>{item.description}</b><small>{item.sku}</small></span><span>{item.quantity} uds.</span><span>{money(item.unit_price)}</span><strong>{money(item.line_total)}</strong></div>)}</div><div className="order-documents"><h3>Documentación</h3>{o.documents?.length?o.documents.map(d=><div className="document-line" key={d.id}><span><b>{d.type} {d.number}</b><small>{new Date(d.created_at).toLocaleString("es-ES")}</small></span><strong>{money(d.total)}</strong>{documentAction(d)}</div>):<p className="small">Este pedido todavía no tiene documentos asociados.</p>}</div></div></details>)}</div>{!filtered.length&&<div className="empty-state"><h2>No hay pedidos</h2><p>Cambia las fechas o el estado seleccionado.</p></div>}</div> }

function Documents({notes,invoices}:{notes:DocumentRow[];invoices:DocumentRow[]}) { return <div className="page"><section className="section"><h1>Mis albaranes</h1>{notes.length?notes.map(x=><div className="doc-row" key={x.id}><div><b>{x.number}</b><div className="small">{x.created_at&&new Date(x.created_at).toLocaleDateString("es-ES")}</div></div><b>{money(x.total)}</b></div>):<p className="small">Todavía no existen albaranes.</p>}</section><section className="section"><h1>Mis facturas</h1>{invoices.length?invoices.map(x=><div className="doc-row" key={x.id}><div><b>{x.number}</b><div className="small">Vencimiento: {x.due_date}</div></div><span className="status">{x.status}</span><b>{money(x.total)}</b></div>):<p className="small">Todavía no existen facturas.</p>}</section></div> }

function Account({user,customer}:{user:User;customer:AccountCustomer|null}) { return <div className="page"><h1>Mi cuenta</h1><div className="section"><h2>{customer?.trade_name||customer?.legal_name||user.name}</h2><p>Razón social: <b>{customer?.legal_name||"—"}</b></p><p>Código cliente EXITERP: <b>{customer?.erp_id||"—"}</b></p><p>NIF/CIF: {customer?.tax_id||"—"}</p><p>Dirección de facturación: {customer?.billing_address||"—"}</p><p>Contacto ERP: {customer?.email||customer?.phone||"—"}</p><p>Usuario de acceso: {user.email}</p></div></div> }

function CartDrawer({cart,stores,onClose,onUpdate,onRemove,onCheckout}:{cart:Cart;stores:Store[];onClose:()=>void;onUpdate:(id:number,q:number)=>void;onRemove:(id:number)=>void;onCheckout:(s:string,j:string,r:string,n:string)=>void}) { const [store,setStore]=useState(cart.store?.id||stores[0]?.id||""); const [job,setJob]=useState(""); const [ref,setRef]=useState(""); const [notes,setNotes]=useState(""); return <><div className="drawer-back" onClick={onClose}/><aside className="drawer"><div className="drawer-head"><div><div className="small">PEDIDO EN PREPARACIÓN</div><h2>Tu pedido</h2></div><button className="close" onClick={onClose}>×</button></div><div className="cart-lines">{cart.items.map(item=><div className="cart-line" key={item.id}><div><b>{item.name}</b><div className="small">{item.sku} · {money(item.unit_price)} por unidad</div><strong className="cart-line-total">{money(item.line_total)}</strong></div><input aria-label={`Cantidad de ${item.name}`} type="number" min="1" value={item.quantity} onChange={e=>onUpdate(item.id,Number(e.target.value))}/><button className="ghost" aria-label={`Eliminar ${item.name}`} onClick={()=>onRemove(item.id)}>×</button></div>)}</div><div className="cart-totals"><div><span>Subtotal sin IVA</span><strong>{money(cart.subtotal)}</strong></div><div><span>IVA</span><strong>{money(cart.tax_total)}</strong></div><div className="cart-grand-total"><span>Total con IVA</span><strong>{money(cart.total)}</strong></div></div><label className="label">Recoger en</label><select className="select" value={store} onChange={e=>setStore(e.target.value)}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select><label className="label">Obra</label><input className="input" value={job} onChange={e=>setJob(e.target.value)} placeholder="Reforma Hotel Coruña"/><label className="label">Referencia cliente</label><input className="input" value={ref} onChange={e=>setRef(e.target.value)} placeholder="OBRA-324"/><label className="label">Observaciones</label><textarea className="textarea" rows={3} value={notes} onChange={e=>setNotes(e.target.value)}/><button className="primary block" disabled={!cart.items.length||!store} onClick={()=>onCheckout(store,job,ref,notes)}>Enviar pedido a tienda</button></aside></> }

function OrderConfirmation({order,onClose,onViewOrders}:{order:Order;onClose:()=>void;onViewOrders:()=>void}) { return <div className="confirmation-back" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)onClose()}}><section className="order-confirmation" role="dialog" aria-modal="true" aria-labelledby="confirmation-title"><button className="confirmation-close" aria-label="Cerrar" onClick={onClose}>×</button><div className="confirmation-icon" aria-hidden="true">✓</div><span className="eyebrow">PEDIDO REGISTRADO</span><h2 id="confirmation-title">¡Pedido recibido!</h2><p>Hemos enviado tu solicitud a <b>{order.store}</b>. Podrás seguir cada paso desde Mis pedidos.</p><div className="confirmation-number"><small>Número de pedido</small><strong>{order.number}</strong></div><div className="confirmation-summary"><span><small>Artículos</small><b>{order.items?.length||0}</b></span><span><small>Total con IVA</small><b>{money(order.total)}</b></span><span><small>Estado</small><b>Registrado</b></span></div><div className="confirmation-next"><b>¿Qué ocurre ahora?</b><span>La tienda revisará el pedido y cambiará su estado cuando entre en preparación.</span></div><div className="confirmation-actions"><button className="ghost" onClick={onClose}>Seguir comprando</button><button className="primary" onClick={onViewOrders}>Ver mis pedidos</button></div></section></div> }

function displayOrderNumber(order:Order) { return order.exit_order_id?.split("/").pop()||order.number.replace(/^EXIT-[^-]*-[^-]*-/,""); }
function orderNumberValue(order:Order) { const value=displayOrderNumber(order); const numeric=Number(value.replace(/\D/g,"")); return Number.isFinite(numeric)?numeric:0; }

function CommandItems({order}:{order:Order}) {
  const [showSga,setShowSga]=useState(false);
  const pending=(item:OrderLine)=>item.pending_quantity??item.quantity;
  const uniqueCount=(items:OrderLine[])=>new Set(items.map(item=>item.sku)).size;
  const renderItems=(items:OrderLine[])=><>{items.map(item=>{const served=pending(item)<=0;return <div className={`dispatch-line ${served?"is-served":""}`} key={`${order.id}-${item.fulfillment_zone}-${item.sku}`}><b>{item.sku}</b><span>{item.description}</span><strong>{served?<em>SERVIDO</em>:<><em>PENDIENTE</em><small>{pending(item).toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</small></>}</strong></div>})}{!items.length&&<p className="dispatch-empty">Sin materiales en esta zona</p>}</>;
  const kardex=(order.items||[]).filter(item=>item.fulfillment_zone==="KARDEX");
  const sga=(order.items||[]).filter(item=>item.fulfillment_zone!=="KARDEX");
  const zoneHeader=(label:string,items:OrderLine[])=><header><h3>{label}</h3><span className={items.length>0&&items.every(item=>pending(item)<=0)?"zone-served":""}>{items.length>0&&items.every(item=>pending(item)<=0)?"SERVIDO":`${uniqueCount(items)} referencias`}</span></header>;
  return <><div className="dispatch-zones"><section className="dispatch-zone zone-KARDEX">{zoneHeader("KARDEX",kardex)}<div className="dispatch-columns"><small>Código</small><small>Material</small><small>Estado</small></div><div className="dispatch-lines">{renderItems(kardex)}</div><footer>Tipos de material <b>{uniqueCount(kardex)}</b></footer></section><button className="sga-popup-trigger" onClick={()=>setShowSga(true)}>SGA {sga.length>0&&<span>{uniqueCount(sga)} referencias</span>}</button></div>{showSga&&<div className="sga-modal-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setShowSga(false)}}><section className="sga-modal" role="dialog" aria-modal="true" aria-label={`Materiales SGA del pedido ${displayOrderNumber(order)}`}><header><div><small>Pedido {displayOrderNumber(order)}</small><h2>SGA</h2></div><button aria-label="Cerrar" onClick={()=>setShowSga(false)}>×</button></header><div className="dispatch-columns"><small>Código</small><small>Material</small><small>Estado</small></div><div className="dispatch-lines">{renderItems(sga)}</div><footer>{uniqueCount(sga)} referencias SGA</footer></section></div>}</>
}

function Operations({orders,onTransition,onRefresh}:{orders:Order[];onTransition:(id:string,status:string)=>Promise<void>;onRefresh:()=>Promise<void>}) {
  const [statusFilter,setStatusFilter]=useState("ACTIVOS");
  const [busyId,setBusyId]=useState<string|null>(null);
  const [collapsed,setCollapsed]=useState<Set<string>>(()=>new Set());
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{const timer=window.setInterval(()=>{setNow(Date.now());onRefresh().catch(()=>{})},15000);return()=>window.clearInterval(timer)},[onRefresh]);
  const stages=[
    {id:"ENVIADO",label:"Nuevos",statuses:["ENVIADO"],action:"",actionLabel:""},
    {id:"RECIBIDO_POR_TIENDA",label:"Aceptados",statuses:["RECIBIDO_POR_TIENDA"],action:"EN_PREPARACION",actionLabel:"Empezar preparación"},
    {id:"EN_PREPARACION",label:"En preparación",statuses:["EN_PREPARACION","PARCIALMENTE_PREPARADO"],action:"LISTO_PARA_RECOGER",actionLabel:"Marcar preparado"},
    {id:"LISTO_PARA_RECOGER",label:"Preparados",statuses:["LISTO_PARA_RECOGER"],action:"ENTREGADO",actionLabel:"Marcar entregado"},
  ];
  const activeStatuses=stages.flatMap(stage=>stage.statuses);
  const operationalOrders=orders.filter(order=>order.status!=="ENTREGADO"&&order.status!=="CANCELADO"&&(order.items||[]).some(item=>(item.pending_quantity??item.quantity)>0));
  const selectedStage=stages.find(stage=>stage.id===statusFilter);
  const visible=operationalOrders.filter(order=>statusFilter==="TODOS"||statusFilter==="ACTIVOS"&&activeStatuses.includes(order.status)||!!selectedStage?.statuses.includes(order.status));
  const sorted=[...visible].sort((a,b)=>orderNumberValue(b)-orderNumberValue(a)||b.number.localeCompare(a.number,"es"));
  const age=(created:string)=>{const mins=Math.max(0,Math.floor((now-new Date(created).getTime())/60000));return mins<60?`${mins} min`:mins<1440?`${Math.floor(mins/60)} h ${mins%60} min`:`${Math.floor(mins/1440)} d`};
  const elapsed=(seconds:number)=>{const total=Math.max(0,Math.floor(seconds));const hours=Math.floor(total/3600);const minutes=Math.floor(total%3600/60);const secs=total%60;return hours>0?`${hours}h ${String(minutes).padStart(2,"0")}m ${String(secs).padStart(2,"0")}s`:`${minutes}m ${String(secs).padStart(2,"0")}s`};
  const advance=async(order:Order,status:string)=>{setBusyId(order.id);try{await onTransition(order.id,status)}finally{setBusyId(null)}};
  const toggleCollapsed=(id:string)=>setCollapsed(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next});
  return <div className="page ops-page"><header className="ops-heading"><div className="ops-titlebar"><span>KARDEX</span><h1>Comandas de pedidos</h1></div><div className="ops-live"><span/> EN DIRECTO</div></header><p className="ops-update-note">↻ Ordenados por número de pedido, actualización automática cada 15 segundos.</p><nav className="ops-filters" aria-label="Filtrar pedidos"><button className={statusFilter==="ACTIVOS"?"active":""} onClick={()=>setStatusFilter("ACTIVOS")}>Activos <b>{operationalOrders.filter(order=>activeStatuses.includes(order.status)).length}</b></button>{stages.map(stage=><button key={stage.id} className={statusFilter===stage.id?"active":""} onClick={()=>setStatusFilter(stage.id)}>{stage.label} <b>{operationalOrders.filter(order=>stage.statuses.includes(order.status)).length}</b></button>)}<button className={statusFilter==="TODOS"?"active":""} onClick={()=>setStatusFilter("TODOS")}>Todos <b>{operationalOrders.length}</b></button><button className="ops-refresh" onClick={()=>onRefresh()}>↻ Actualizar</button></nav><div className="dispatch-list">{sorted.map(order=>{const stage=stages.find(item=>item.statuses.includes(order.status));const registered=new Date(order.created_at);const references=new Set((order.items||[]).map(item=>item.sku)).size;const isCollapsed=collapsed.has(order.id);const items=order.items||[];const kardexItems=items.filter(item=>item.fulfillment_zone==="KARDEX");const hasKardex=kardexItems.length>0;const liveSeconds=Math.max(0,Math.floor((now-registered.getTime())/1000));const servedLines=kardexItems.filter(item=>(item.pending_quantity??item.quantity)<=0).length;const progress=kardexItems.length?Math.round(servedLines/kardexItems.length*100):0;return <article className={`dispatch-order ${isCollapsed?"is-collapsed":""}`} key={order.id}><header className="dispatch-header"><div className="dispatch-summary-top"><div className="dispatch-order-number"><small>N.º pedido</small><strong>{displayOrderNumber(order)}</strong></div><span className="process-badge">◷ EN PROCESO</span><div className="dispatch-progress"><b>{hasKardex?elapsed(order.kardex_duration_seconds??liveSeconds):"—"}</b><span><small>{servedLines}/{kardexItems.length}</small><i><em style={{width:`${progress}%`}}/></i><strong>{progress}%</strong></span></div></div><div className="dispatch-meta-grid"><div><small>Cliente</small><strong>{order.customer}</strong><span>Código: {order.customer_code||"—"}</span></div><div><small>Registro</small><strong>{registered.toLocaleDateString("es-ES")}</strong><span>{registered.toLocaleTimeString("es-ES")} · hace {age(order.created_at)}</span></div><div><small>Materiales</small><strong>{references} referencias</strong><span>{items.length} líneas</span></div><div><small>Usuario que generó el pedido</small><strong>{order.created_by||"—"}</strong></div><div><small>Estado</small><strong>{statusLabel(order.status)}</strong>{stage?.action&&<button disabled={busyId===order.id} onClick={()=>advance(order,stage.action)}>{busyId===order.id?"Actualizando…":stage.actionLabel}</button>}</div></div></header><button className="dispatch-collapse" aria-expanded={!isCollapsed} onClick={()=>toggleCollapsed(order.id)}>{isCollapsed?"Ver detalle ⌄":"Ocultar detalle ⌃"}</button>{!isCollapsed&&<>{order.notes&&<div className="dispatch-note"><b>Observaciones:</b> {order.notes}</div>}<CommandItems order={order}/></>}</article>})}{!sorted.length&&<div className="ops-empty"><span>✓</span><h2>No hay pedidos pendientes</h2><p>Los pedidos servidos se retiran automáticamente del tablero.</p></div>}</div></div>
}
