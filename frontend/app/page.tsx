"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

type View = "home" | "catalog" | "quick" | "orders" | "documents" | "ops" | "account";
type User = { id: string; name: string; email: string; role: string };
type AccountCustomer = { trade_name: string; legal_name: string; erp_id: string; discount_pct: number };
type Store = { id: string; code: string; name: string; address: string };
type Stock = { store_code: string; store: string; available: number };
type Suggestion = { id: string; sku: string; name: string; price: number; area_id: number; family_id: number; subfamily_id: number; product_type_id: number };
type Product = { id: string; image_url: string; sku: string; name: string; brand: string; family: string; customer_price: number; list_price: number; price_with_tax: number; price_without_tax: number; tax_rate: number; total_available: number; stock: Stock[] };
type CartItem = { id: number; product_id: string; sku: string; name: string; quantity: number; unit_price: number; line_total: number };
type Cart = { items: CartItem[]; line_count: number; subtotal: number; tax_total: number; total: number; store: { id: string; name: string } | null };
type Order = { id: string; number: string; status: string; store: string; customer_reference?: string; job_name?: string; total: number; created_at: string; items?: CartItem[] };
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
    setCartOpen(false); setView("orders"); await refreshCustomerData(); alert(`Pedido ${order.number} enviado correctamente`);
  }

  if (loading) return <div className="loading">Preparando el portal profesional…</div>;
  if (!user) return <Login onLogin={login} error={error} />;

  return <main className="shell">
    <header className="header">
      <div className="head">
        <button className="brand" onClick={() => setView(isOperator ? "ops" : "home")} aria-label="Inicio"><img src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa · 25 aniversario" /></button>
        {!isOperator && <div className="global-search">
          <form className="search-form" onSubmit={e => { e.preventDefault(); setView("catalog"); setSuggestionsEnabled(false); setSuggestions([]); searchProducts().catch(e=>setError(e.message)); }}>
            <select aria-label="Departamento" value={catalogFilters.areaId} onChange={e=>{setCatalogFilters({areaId:e.target.value,familyId:"",subfamilyId:"",productTypeId:""});setView("catalog")}}><option value="">Todos los departamentos</option>{classification.map(area=><option key={area.id} value={area.id}>{area.name}</option>)}</select>
            <input aria-label="Buscar productos" value={query} onChange={e => {setQuery(e.target.value);setSuggestionsEnabled(true);setCatalogFilters(emptyCatalogFilters);setView("catalog")}} onKeyDown={e=>{if(e.key==="Escape"){setSuggestionsEnabled(false);setSuggestions([])}}} placeholder="Busca por producto, referencia o medida" />
            {!!query && <button className="search-clear" aria-label="Limpiar búsqueda" type="button" onClick={()=>{setQuery("");setCatalogFilters(emptyCatalogFilters);setSuggestionsEnabled(false);setSuggestions([]);setView("catalog")}}>×</button>}
            <button className="search-submit" aria-label="Buscar" type="submit">⌕</button>
          </form>
          {!!suggestions.length && <div className="suggestions" role="listbox" aria-label="Sugerencias de productos">{suggestions.map(p => <button className="suggestion" role="option" key={p.id} onClick={() => {setSuggestionsEnabled(false);setQuery(p.name);setCatalogFilters({areaId:String(p.area_id),familyId:String(p.family_id),subfamilyId:String(p.subfamily_id),productTypeId:String(p.product_type_id)});setSuggestions([]);setView("catalog")}}><span><b>{p.name}</b><br/><small>Código {p.sku}</small></span><span className="suggestion-side"><b>{money(p.price)}</b><small>Ver producto →</small></span></button>)}</div>}
        </div>}
        <button className="account-button" onClick={()=>setView("account")}><small>Hola, {user.name.split(" ")[0]}</small><b>Mi cuenta</b></button><button className="logout-button" onClick={logout}>Salir</button>
        {!isOperator && <button className="cart-button" onClick={() => setCartOpen(true)}>▤ <span>Mi carrito</span> {cart?.line_count || 0}</button>}
      </div>
      <nav className="desktop-nav">{(isOperator ? [["ops","Operaciones"]] : [["home","Inicio"],["catalog","Catálogo"],["quick","Pedido rápido"],["orders","Mis pedidos"],["documents","Albaranes y facturas"],["account","Mi cuenta"]]).map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>
    </header>
    <div className="service-strip"><span>ÁREA PROFESIONAL · Compra a tu ritmo</span><span>5 delegaciones · Recogida en tienda</span></div>{error && <div className="page error" role="alert">{error}</div>}
    {view === "home" && <Home customer={customer} orders={orders} products={products.slice(0,8)} onNavigate={setView} onAdd={addProduct} onRepeat={repeatOrder} />}
    {view === "catalog" && <Catalog products={products} total={totalProducts} classification={classification} filters={catalogFilters} setFilters={setCatalogFilters} onAdd={addProduct} />}
    {view === "quick" && <QuickOrder onResolve={async (lines) => { for (const line of lines) { const result = await api<{items:Product[]}>(`/api/v1/products?q=${encodeURIComponent(line.query)}&page_size=1`); if (result.items[0]) await addProduct(result.items[0].id, line.qty); } setCartOpen(true); }} />}
    {view === "orders" && <Orders orders={orders} onRepeat={repeatOrder} />}
    {view === "documents" && <Documents notes={deliveryNotes} invoices={invoices} />}
    {view === "account" && <Account user={user} customer={customer} />}
    {view === "ops" && <Operations orders={opsOrders} onTransition={async (id,status) => { await api(`/api/v1/store/orders/${id}/transitions`, {method:"POST",body:JSON.stringify({status})}); setOpsOrders(await api<Order[]>("/api/v1/store/orders")); }} />}
    {!isOperator && <nav className="mobile-nav">{[["home","Inicio"],["catalog","Buscar"],["quick","Pedido"],["orders","Pedidos"],["account","Cuenta"]].map(([id,label]) => <button key={id} className={view===id?"active":""} onClick={() => setView(id as View)}>{label}</button>)}</nav>}
    {cartOpen && cart && <CartDrawer cart={cart} stores={stores} onClose={() => setCartOpen(false)} onUpdate={updateCart} onRemove={removeCart} onCheckout={checkout} />}
  </main>;
}

function Login({onLogin,error}:{onLogin:(email:string,password:string)=>Promise<void>;error:string}) {
  const [loginError,setLoginError]=useState(""); const [email,setEmail]=useState("compras001@cliente.test"); const [password,setPassword]=useState("123456"); const [busy,setBusy]=useState(false);
  async function submit(e:FormEvent){e.preventDefault();setBusy(true);try{await onLogin(email,password)}catch(e){setLoginError((e as Error).message)}finally{setBusy(false)}}
  return <div className="login"><section className="login-brand"><img className="login-logo" src="/bermudez-ulloa-logo.jpg" alt="Bermúdez Ulloa"/><h1>Material profesional.<br/>Pedido en segundos.</h1><p>Consulta tu precio, comprueba stock local y deja el pedido preparado en cualquiera de nuestras cinco delegaciones.</p></section><section className="login-panel"><form className="login-form" onSubmit={submit}><h2>Acceso profesional</h2><p className="small">Entra con la cuenta de tu empresa.</p><label className="label">Email</label><input className="input" value={email} onChange={e=>setEmail(e.target.value)}/><label className="label">Contraseña</label><input className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)}/>{(error||loginError)&&<p className="error">{error||loginError}</p>}<button className="primary block" disabled={busy}>{busy?"Entrando…":"Iniciar sesión"}</button><div className="hint">Cliente demo: compras001@cliente.test<br/>Operador: operador@bermudez.test<br/>Contraseña: 123456</div></form></section></div>
}

function Home({customer,orders,products,onNavigate,onAdd,onRepeat}:{customer:AccountCustomer|null;orders:Order[];products:Product[];onNavigate:(v:View)=>void;onAdd:(id:string)=>void;onRepeat:(id:string)=>void}) {
  const active = orders.filter(o=>o.status!=="ENTREGADO"&&o.status!=="CANCELADO");
  return <div className="page"><section className="hero"><div><span className="eyebrow">TU MOSTRADOR DIGITAL</span><h1>Todo lo que necesitas.<br/>Listo para tu próxima obra.</h1><p>Hola, {customer?.trade_name || "profesional"}. Encuentra tu material y recógelo en tienda.</p><button className="primary" onClick={()=>onNavigate("catalog")}>Explorar catálogo →</button></div><div className="hero-note"><span>01 / BUSCA</span><span>02 / AÑADE</span><span>03 / RECOGE</span><b>Menos esperas.<br/>Más tiempo en obra.</b></div></section>
  <div className="home-grid"><div><section className="shortcut-grid"><button onClick={()=>onNavigate("quick")}><span>↗</span><b>Pedido rápido</b><small>Pega referencias y cantidades</small></button><button onClick={()=>onNavigate("documents")}><span>▤</span><b>Tus documentos</b><small>Facturas y albaranes a mano</small></button><button disabled={!orders.length} onClick={()=>orders[0]&&onRepeat(orders[0].id)}><span>↻</span><b>Vuelve a pedir</b><small>Repite tu último pedido</small></button></section><section className="section panel"><div className="section-heading"><div><span className="eyebrow">MATERIAL PARA TU DÍA A DÍA</span><h2>Explora el catálogo</h2></div><button className="text-button" onClick={()=>onNavigate("catalog")}>Ver todo →</button></div><div className="products">{products.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd}/>)}</div></section></div>
  <aside className="activity-panel panel"><div className="section-heading"><h2>Mis pedidos</h2><span className="count">{active.length}</span></div><p className="small">El estado de tus últimas compras.</p>{active.slice(0,3).map(o=><div className="compact-order" key={o.id}><b>{o.number}</b><span className="small">{o.store} · {o.job_name||"Sin obra"}</span><span className="status">{statusLabel(o.status)}</span></div>)}{!active.length&&<p className="small">No tienes pedidos activos.</p>}<button className="ghost block" onClick={()=>onNavigate("orders")}>Ver todos mis pedidos →</button><div className="store-note"><b>Cerca de tu próxima obra</b><p>Almeiras · A Coruña · Sanxenxo · Ferrol · Santiago</p></div></aside></div></div>;
}

function Catalog({products,total,classification,filters,setFilters,onAdd}:{products:Product[];total:number;classification:AreaNode[];filters:CatalogFilters;setFilters:(f:CatalogFilters)=>void;onAdd:(id:string,qty?:number)=>void}) {
  const selectArea=(id:number|string)=>setFilters({areaId:String(id),familyId:"",subfamilyId:"",productTypeId:""});
  const selectFamily=(areaId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(id),subfamilyId:"",productTypeId:""});
  const selectSubfamily=(areaId:number,familyId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(familyId),subfamilyId:String(id),productTypeId:""});
  const selectType=(areaId:number,familyId:number,subfamilyId:number,id:number)=>setFilters({areaId:String(areaId),familyId:String(familyId),subfamilyId:String(subfamilyId),productTypeId:String(id)});
  return <div className="page"><div className="toolbar"><div><h1>Catálogo profesional</h1><div className="small">{total.toLocaleString("es-ES")} referencias encontradas</div></div>{(filters.areaId||filters.familyId||filters.subfamilyId||filters.productTypeId)&&<button className="ghost" onClick={()=>setFilters(emptyCatalogFilters)}>Limpiar clasificación</button>}</div><div className="catalog-layout"><aside className="category-panel"><h2>Departamentos</h2><button className={`tree-all ${!filters.areaId?"active":""}`} onClick={()=>setFilters(emptyCatalogFilters)}>Todos los departamentos</button><div className="catalog-tree">{classification.map(area=><details key={area.id} open={filters.areaId===String(area.id)}><summary><button className={filters.areaId===String(area.id)&&!filters.familyId?"active":""} onClick={e=>{e.preventDefault();selectArea(area.id)}}>{area.name}<span>{area.count}</span></button></summary><div className="tree-level family-level">{area.families.map(family=><details key={family.id} open={filters.familyId===String(family.id)}><summary><button className={filters.familyId===String(family.id)&&!filters.subfamilyId?"active":""} onClick={e=>{e.preventDefault();selectFamily(area.id,family.id)}}>{family.name}<span>{family.count}</span></button></summary><div className="tree-level subfamily-level">{family.subfamilies.map(subfamily=><details key={subfamily.id} open={filters.subfamilyId===String(subfamily.id)}><summary><button className={filters.subfamilyId===String(subfamily.id)&&!filters.productTypeId?"active":""} onClick={e=>{e.preventDefault();selectSubfamily(area.id,family.id,subfamily.id)}}>{subfamily.name}<span>{subfamily.count}</span></button></summary><div className="tree-level type-level">{subfamily.product_types.map(type=><button key={type.id} className={filters.productTypeId===String(type.id)?"active":""} onClick={()=>selectType(area.id,family.id,subfamily.id,type.id)}>{type.name}<span>{type.count}</span></button>)}</div></details>)}</div></details>)}</div></details>)}</div></aside><section><div className="products">{products.map(p=><ProductCard key={p.id} product={p} onAdd={onAdd}/>)}</div>{!products.length&&<div className="empty-state"><h2>No encontramos ese material</h2><p>Prueba otra referencia, menos palabras o limpia la clasificación seleccionada.</p></div>}</section></div></div>
}

function ProductCard({product,onAdd}:{product:Product;onAdd:(id:string,qty?:number)=>void}) { const [qty,setQty]=useState(1); const [imageFailed,setImageFailed]=useState(false); return <article className="product"><div className={`product-visual ${imageFailed?"image-missing":""}`}>{!imageFailed?<img src={product.image_url} alt={product.name} loading="lazy" onError={()=>setImageFailed(true)}/>:<><span aria-hidden="true">{product.family.slice(0,2).toUpperCase()}</span><small>{product.family}</small></>}</div><span className="family-name">{product.family}</span><h3>{product.name}</h3><span className="sku">{product.sku} · {product.brand}</span><div className="price">{money(product.price_with_tax)}</div><span className="small">IVA incluido · <b>{money(product.price_without_tax)}</b> sin IVA</span><div className="stock-popover" tabIndex={0} aria-label={`Stock total ${product.total_available} unidades. Ver detalle por almacén`}><div className="stock">● {Math.max(0,Math.round(product.total_available))} uds. disponibles <span aria-hidden="true">ⓘ</span></div><div className="stock-detail" role="tooltip"><b>Stock por almacén</b>{product.stock.length?product.stock.map(item=><div className="stock-row" key={item.store_code}><span>{item.store}<small>Almacén {item.store_code}</small></span><strong>{item.available.toLocaleString("es-ES",{maximumFractionDigits:2})} uds.</strong></div>):<p>Sin existencias en los almacenes incluidos.</p>}<div className="stock-note">No incluye los almacenes configurados como excluidos.</div></div></div><div className="product-actions"><input className="qty" type="number" min="1" value={qty} onChange={e=>setQty(Math.max(1,Number(e.target.value)))}/><button className="secondary block" onClick={()=>onAdd(product.id,qty)}>Añadir al carrito</button></div></article> }

function QuickOrder({onResolve}:{onResolve:(lines:{query:string;qty:number}[])=>Promise<void>}) { const [text,setText]=useState("B2B000001 | 10\ncodo 22 | 15\nracor marsella | 4"); const [busy,setBusy]=useState(false); async function process(){const lines=text.split("\n").map(x=>x.trim()).filter(Boolean).map(line=>{const parts=line.split(/[|;]/);return{query:parts[0].trim(),qty:Math.max(1,Number(parts[1])||1)}});setBusy(true);try{await onResolve(lines)}finally{setBusy(false)}} return <div className="page"><h1>Pedido rápido</h1><p className="small">Escribe o pega una línea por producto: referencia o descripción | cantidad.</p><textarea className="textarea" rows={10} value={text} onChange={e=>setText(e.target.value)}/><button className="primary" onClick={process} disabled={busy}>{busy?"Buscando referencias…":"Añadir líneas al pedido"}</button></div> }

function Orders({orders,onRepeat}:{orders:Order[];onRepeat:(id:string)=>void}) { return <div className="page"><h1>Mis pedidos</h1>{orders.map(o=><div className="order-row" key={o.id}><div><b>{o.number}</b><div className="small">{new Date(o.created_at).toLocaleString("es-ES")} · {o.store} · {o.job_name||"Sin obra"}</div></div><div><b>{money(o.total)}</b><br/><span className="status">{statusLabel(o.status)}</span></div><button className="ghost" onClick={()=>onRepeat(o.id)}>Repetir pedido</button></div>)}</div> }

function Documents({notes,invoices}:{notes:DocumentRow[];invoices:DocumentRow[]}) { return <div className="page"><section className="section"><h1>Mis albaranes</h1>{notes.length?notes.map(x=><div className="doc-row" key={x.id}><div><b>{x.number}</b><div className="small">{x.created_at&&new Date(x.created_at).toLocaleDateString("es-ES")}</div></div><b>{money(x.total)}</b></div>):<p className="small">Todavía no existen albaranes.</p>}</section><section className="section"><h1>Mis facturas</h1>{invoices.length?invoices.map(x=><div className="doc-row" key={x.id}><div><b>{x.number}</b><div className="small">Vencimiento: {x.due_date}</div></div><span className="status">{x.status}</span><b>{money(x.total)}</b></div>):<p className="small">Todavía no existen facturas.</p>}</section></div> }

function Account({user,customer}:{user:User;customer:AccountCustomer|null}) { return <div className="page"><h1>Mi cuenta</h1><div className="section"><h2>{customer?.legal_name||user.name}</h2><p>Código cliente: <b>{customer?.erp_id||"—"}</b></p><p>Usuario: {user.email}</p><p>Rol: {user.role}</p><p>Descuento comercial de demostración: {customer?.discount_pct||0}%</p></div></div> }

function CartDrawer({cart,stores,onClose,onUpdate,onRemove,onCheckout}:{cart:Cart;stores:Store[];onClose:()=>void;onUpdate:(id:number,q:number)=>void;onRemove:(id:number)=>void;onCheckout:(s:string,j:string,r:string,n:string)=>void}) { const [store,setStore]=useState(cart.store?.id||stores[0]?.id||""); const [job,setJob]=useState(""); const [ref,setRef]=useState(""); const [notes,setNotes]=useState(""); return <><div className="drawer-back" onClick={onClose}/><aside className="drawer"><div className="drawer-head"><div><div className="small">PEDIDO EN PREPARACIÓN</div><h2>Tu pedido</h2></div><button className="close" onClick={onClose}>×</button></div>{cart.items.map(item=><div className="cart-line" key={item.id}><div><b>{item.name}</b><div className="small">{item.sku} · {money(item.unit_price)}</div></div><input type="number" min="1" value={item.quantity} onChange={e=>onUpdate(item.id,Number(e.target.value))}/><button className="ghost" onClick={()=>onRemove(item.id)}>×</button></div>)}<div className="total"><span>Total sin IVA</span><span>{money(cart.subtotal)}</span></div><label className="label">Recoger en</label><select className="select" value={store} onChange={e=>setStore(e.target.value)}>{stores.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select><label className="label">Obra</label><input className="input" value={job} onChange={e=>setJob(e.target.value)} placeholder="Reforma Hotel Coruña"/><label className="label">Referencia cliente</label><input className="input" value={ref} onChange={e=>setRef(e.target.value)} placeholder="OBRA-324"/><label className="label">Observaciones</label><textarea className="textarea" rows={3} value={notes} onChange={e=>setNotes(e.target.value)}/><button className="primary block" disabled={!cart.items.length||!store} onClick={()=>onCheckout(store,job,ref,notes)}>Enviar pedido a tienda</button></aside></> }

function Operations({orders,onTransition}:{orders:Order[];onTransition:(id:string,status:string)=>void}) { const groups=["ENVIADO","RECIBIDO_POR_TIENDA","EN_PREPARACION","LISTO_PARA_RECOGER"]; const next:Record<string,string>={ENVIADO:"RECIBIDO_POR_TIENDA",RECIBIDO_POR_TIENDA:"EN_PREPARACION",EN_PREPARACION:"LISTO_PARA_RECOGER",LISTO_PARA_RECOGER:"ENTREGADO"}; return <div className="page"><h1>Panel de tienda</h1><div className="ops">{groups.map(status=><section className="lane" key={status}><b>{statusLabel(status)} · {orders.filter(o=>o.status===status).length}</b>{orders.filter(o=>o.status===status).map(o=><article className="ticket" key={o.id}><b>{o.number}</b><div>{o.job_name||"Sin obra"}</div><div className="small">{o.items?.length||0} líneas · {money(o.total)}</div><button className="secondary block" onClick={()=>onTransition(o.id,next[status])}>{status==="LISTO_PARA_RECOGER"?"Marcar entregado":"Avanzar estado"}</button></article>)}</section>)}</div></div> }
