import { useEffect, useMemo, useState } from "react";
import { api, getUserId, setUserId } from "./api";

const DOC_TYPES = [
  "Bank Statement",
  "Sales Register",
  "Purchase Register",
  "GST Return",
  "Expense Summary",
];

function statusClass(status) {
  switch (status) {
    case "Approved":
      return "bg-emerald-100 text-emerald-800";
    case "Correction Required":
      return "bg-amber-100 text-amber-900";
    case "Under Review":
      return "bg-sky-100 text-sky-900";
    case "Uploaded":
      return "bg-stone-200 text-stone-800";
    default:
      return "bg-stone-100 text-stone-600";
  }
}

function Badge({ children }) {
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${statusClass(children)}`}>
      {children}
    </span>
  );
}

function formatWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { hour12: true });
}

export default function App() {
  const [users, setUsers] = useState([]);
  const [me, setMe] = useState(null);
  const [view, setView] = useState("clients");
  const [clients, setClients] = useState([]);
  const [selectedClient, setSelectedClient] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [audit, setAudit] = useState([]);
  const [firmAudit, setFirmAudit] = useState([]);
  const [error, setError] = useState("");
  const [newClient, setNewClient] = useState("");
  const [newType, setNewType] = useState(DOC_TYPES[0]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [pickFirm, setPickFirm] = useState("");
  const [pickUser, setPickUser] = useState("");
  const [newFile, setNewFile] = useState(null);

  async function loadSession() {
    const list = await api.users();
    setUsers(list);
    const id = getUserId();
    if (!id) {
      setMe(null);
      return;
    }
    try {
      const current = await api.me();
      setMe(current);
    } catch {
      setUserId(null);
      setMe(null);
    }
  }

  useEffect(() => {
    loadSession().catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!me) return;
    setError("");
    api
      .clients()
      .then(setClients)
      .catch((e) => setError(e.message));
  }, [me]);

  const usersByFirm = useMemo(() => {
    const map = {};
    for (const u of users) {
      map[u.firm_name] = map[u.firm_name] || [];
      map[u.firm_name].push(u);
    }
    return map;
  }, [users]);

  async function login(id) {
    setUserId(id);
    const current = await api.me();
    setMe(current);
    setView("clients");
    setSelectedClient(null);
    setSelectedDoc(null);
  }

  function logout() {
    setUserId(null);
    setMe(null);
    setClients([]);
    setDocuments([]);
    setSelectedClient(null);
    setSelectedDoc(null);
  }

  async function openClient(c) {
    setSelectedClient(c);
    setView("client");
    const docs = await api.documents(c.id);
    setDocuments(docs);
  }

  async function refreshDoc(id) {
    const doc = await api.document(id);
    setSelectedDoc(doc);
    const events = await api.documentAudit(id);
    setAudit(events);
    if (selectedClient) {
      setDocuments(await api.documents(selectedClient.id));
    }
    return doc;
  }

  async function openDoc(doc) {
    setView("document");
    await refreshDoc(doc.id);
  }

  async function openFirmAudit() {
    setView("audit");
    setFirmAudit(await api.firmAudit());
  }

  if (!me) {
    const firmNames = Object.keys(usersByFirm);
    const members = pickFirm ? usersByFirm[pickFirm] || [] : [];
    return (
      <div className="mx-auto max-w-lg px-6 py-16">
        <p className="text-xs font-medium uppercase tracking-widest text-stone-500">
          Mini Audit Document Review
        </p>
        <h1 className="mt-2 text-3xl font-semibold">Sign in</h1>
        <p className="mt-3 text-sm text-stone-600">
          Mock login: pick a firm and a role. Authentication is not authorization — every
          API query is still scoped by <span className="font-mono text-xs">firm_id</span>{" "}
          on the server. Hiding a button is not security.
        </p>
        {error && <p className="mt-4 text-sm text-red-700">{error}</p>}
        <form
          className="mt-8 space-y-4 rounded-lg border border-stone-200 bg-white p-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (!pickUser) return;
            login(Number(pickUser)).catch((err) => setError(err.message));
          }}
        >
          <label className="block text-sm">
            Firm
            <select
              className="mt-1 w-full rounded border border-stone-300 px-3 py-2"
              value={pickFirm}
              onChange={(e) => {
                setPickFirm(e.target.value);
                setPickUser("");
              }}
              required
            >
              <option value="">Select firm</option>
              {firmNames.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            User / role
            <select
              className="mt-1 w-full rounded border border-stone-300 px-3 py-2"
              value={pickUser}
              onChange={(e) => setPickUser(e.target.value)}
              required
              disabled={!pickFirm}
            >
              <option value="">Select staff or reviewer</option>
              {members.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name} ({u.role})
                </option>
              ))}
            </select>
          </label>
          <button className="w-full rounded bg-stone-900 px-3 py-2 text-sm text-white" type="submit">
            Continue
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div>
            <p className="text-xs uppercase tracking-widest text-stone-500">{me.firm_name}</p>
            <p className="font-medium">
              {me.name}{" "}
              <span className="font-mono text-xs uppercase text-stone-500">{me.role}</span>
            </p>
          </div>
          <nav className="flex gap-4 text-sm">
            <button onClick={() => setView("clients")} className="hover:underline">
              Clients
            </button>
            <button onClick={openFirmAudit} className="hover:underline">
              Audit history
            </button>
            <button onClick={logout} className="text-stone-500 hover:underline">
              Switch user
            </button>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}

        {view === "clients" && (
          <section>
            <div className="flex items-end justify-between gap-4">
              <div>
                <h1 className="text-2xl font-semibold">Clients</h1>
                <p className="text-sm text-stone-600">Only clients belonging to {me.firm_name}.</p>
              </div>
              {me.role === "staff" && (
                <form
                  className="flex gap-2"
                  onSubmit={async (e) => {
                    e.preventDefault();
                    setBusy(true);
                    try {
                      await api.createClient(newClient);
                      setNewClient("");
                      setClients(await api.clients());
                    } catch (err) {
                      setError(err.message);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <input
                    className="rounded border border-stone-300 px-3 py-2 text-sm"
                    placeholder="New client name"
                    value={newClient}
                    onChange={(e) => setNewClient(e.target.value)}
                    required
                  />
                  <button
                    disabled={busy}
                    className="rounded bg-stone-900 px-3 py-2 text-sm text-white"
                  >
                    Create
                  </button>
                </form>
              )}
            </div>
            <ul className="mt-6 divide-y divide-stone-200 rounded-lg border border-stone-200 bg-white">
              {clients.map((c) => (
                <li key={c.id}>
                  <button
                    className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-stone-50"
                    onClick={() => openClient(c).catch((e) => setError(e.message))}
                  >
                    <span>{c.name}</span>
                    <span className="text-xs text-stone-400">#{c.id}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {view === "client" && selectedClient && (
          <section>
            <button className="text-sm text-stone-500 hover:underline" onClick={() => setView("clients")}>
              ← Clients
            </button>
            <h1 className="mt-2 text-2xl font-semibold">{selectedClient.name}</h1>
            {me.role === "staff" && (
              <form
                className="mt-4 flex flex-wrap items-end gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  if (!newFile) {
                    setError("Choose a file. The list shows its name and Uploaded status right after save.");
                    return;
                  }
                  setBusy(true);
                  setError("");
                  try {
                    const saved = await api.createDocumentWithFile(
                      selectedClient.id,
                      newType,
                      newFile
                    );
                    setNewFile(null);
                    form.reset();
                    const rows = await api.documents(selectedClient.id);
                    const others = rows.filter((d) => d.id !== saved.id);
                    setDocuments([saved, ...others]);
                  } catch (err) {
                    setError(err.message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                <label className="text-sm">
                  Document type
                  <select
                    className="mt-1 block rounded border border-stone-300 px-3 py-2"
                    value={newType}
                    onChange={(e) => setNewType(e.target.value)}
                  >
                    {DOC_TYPES.map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                </label>
                <label className="text-sm">
                  File
                  <input
                    type="file"
                    className="mt-1 block text-sm"
                    required
                    onChange={(e) => setNewFile(e.target.files?.[0] || null)}
                  />
                </label>
                <button className="rounded bg-stone-900 px-3 py-2 text-sm text-white" disabled={busy}>
                  {busy ? "Uploading…" : "Add document"}
                </button>
              </form>
            )}
            <table className="mt-6 w-full border-collapse overflow-hidden rounded-lg border border-stone-200 bg-white text-sm">
              <thead className="bg-stone-50 text-left text-stone-500">
                <tr>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">File</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr
                    key={d.id}
                    className="cursor-pointer border-t border-stone-100 hover:bg-stone-50"
                    onClick={() => openDoc(d).catch((e) => setError(e.message))}
                  >
                    <td className="px-3 py-2">{d.doc_type}</td>
                    <td className="px-3 py-2 font-medium">
                      {d.current_filename || d.versions?.[d.versions.length - 1]?.original_filename || "No file yet"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge>{d.current_status}</Badge>
                    </td>
                    <td className="px-3 py-2">{formatWhen(d.uploaded_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

        {view === "document" && selectedDoc && (
          <ReviewScreen
            me={me}
            doc={selectedDoc}
            audit={audit}
            comment={comment}
            setComment={setComment}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            refreshDoc={refreshDoc}
            onDeleted={async () => {
              setSelectedDoc(null);
              setView("client");
              if (selectedClient) {
                setDocuments(await api.documents(selectedClient.id));
              }
            }}
            onBack={() => {
              setView("client");
              setSelectedDoc(null);
            }}
          />
        )}

        {view === "audit" && (
          <section>
            <h1 className="text-2xl font-semibold">Audit history</h1>
            <p className="text-sm text-stone-600">
              Firm-scoped events only. {me.firm_name} cannot see another firm’s trail.
            </p>
            <ol className="mt-6 space-y-3">
              {firmAudit.map((e) => (
                <li key={e.id} className="rounded-lg border border-stone-200 bg-white px-4 py-3 text-sm">
                  <p>{e.display_text}</p>
                  <p className="mt-1 font-mono text-xs text-stone-500">
                    {e.actor} ({e.actor_role}) · {e.action} · {e.from_status || "—"} → {e.to_status || "—"}
                  </p>
                </li>
              ))}
            </ol>
          </section>
        )}
      </main>
    </div>
  );
}

function ReviewScreen({
  me,
  doc,
  audit,
  comment,
  setComment,
  busy,
  setBusy,
  setError,
  refreshDoc,
  onDeleted,
  onBack,
}) {
  const latest = doc.versions?.[doc.versions.length - 1];

  async function run(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refreshDoc(doc.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="grid gap-8 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <button className="text-sm text-stone-500 hover:underline" onClick={onBack}>
          ← Back
        </button>
        <h1 className="mt-2 text-2xl font-semibold">{doc.current_filename || doc.doc_type}</h1>
        <dl className="mt-4 grid grid-cols-2 gap-3 rounded-lg border border-stone-200 bg-white p-4 text-sm">
          <div>
            <dt className="text-stone-500">Document name</dt>
            <dd className="font-medium">{doc.current_filename || "(not uploaded)"}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Client</dt>
            <dd className="font-medium">{doc.client_name}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Uploaded by</dt>
            <dd className="font-medium">{doc.uploaded_by_name || "—"}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Upload date/time</dt>
            <dd className="font-medium">{formatWhen(doc.uploaded_at)}</dd>
          </div>
          <div>
            <dt className="text-stone-500">Current status</dt>
            <dd>
              <Badge>{doc.current_status}</Badge>
            </dd>
          </div>
          <div>
            <dt className="text-stone-500">Review comment</dt>
            <dd className="font-medium">{doc.latest_review_comment || "—"}</dd>
          </div>
        </dl>

        {latest && (
          <p className="mt-3 font-mono text-xs text-stone-500">
            SHA-256 {latest.checksum_sha256}
          </p>
        )}
        <p className="mt-1 text-xs text-stone-500">
          Dataset files are seeded from AgamiAI bank statements, synthetic-finance-data,
          invoice-sandbox-benchmark, and LedgerBridge — one file per document type.
        </p>

        <div className="mt-4 flex flex-wrap gap-2">
          {doc.current_filename && (
            <button
              className="rounded border border-stone-300 bg-white px-3 py-2 text-sm"
              onClick={() =>
                api.download(doc.id, null, doc.current_filename).catch((e) => setError(e.message))
              }
            >
              Download current file
            </button>
          )}
          {me.role === "staff" && (
            <button
              disabled={busy}
              className="rounded border border-red-300 bg-white px-3 py-2 text-sm text-red-700"
              onClick={async () => {
                if (!window.confirm("Delete this document? Audit history is kept.")) return;
                setBusy(true);
                setError("");
                try {
                  await api.deleteDocument(doc.id);
                  await onDeleted();
                } catch (err) {
                  setError(err.message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Delete document
            </button>
          )}
        </div>

        {me.role === "staff" &&
          (doc.current_status === "Pending" || doc.current_status === "Correction Required") && (
            <label className="mt-6 block text-sm">
              {doc.current_status === "Correction Required" ? "Re-upload revised file" : "Upload file"}
              <input
                type="file"
                className="mt-1 block"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  run(() => api.upload(doc.id, file));
                }}
              />
            </label>
          )}

        {me.role === "reviewer" && doc.current_status === "Uploaded" && (
          <button
            disabled={busy}
            className="mt-6 rounded bg-stone-900 px-3 py-2 text-sm text-white"
            onClick={() => run(() => api.startReview(doc.id))}
          >
            Start review
          </button>
        )}

        {me.role === "reviewer" && doc.current_status === "Under Review" && (
          <div className="mt-6 space-y-3 rounded-lg border border-stone-200 bg-white p-4">
            <button
              disabled={busy}
              className="rounded bg-emerald-700 px-3 py-2 text-sm text-white"
              onClick={() => run(() => api.approve(doc.id))}
            >
              Approve
            </button>
            <label className="block text-sm">
              Correction comment (required to request correction)
              <textarea
                className="mt-1 w-full rounded border border-stone-300 px-3 py-2"
                rows={3}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Page 3 is missing. Please upload the complete bank statement."
              />
            </label>
            <button
              disabled={busy}
              className="rounded bg-amber-700 px-3 py-2 text-sm text-white"
              onClick={() =>
                run(async () => {
                  await api.requestCorrection(doc.id, comment);
                  setComment("");
                })
              }
            >
              Request correction
            </button>
          </div>
        )}

        <div className="mt-8">
          <h2 className="font-medium">Versions</h2>
          <ul className="mt-2 space-y-2 text-sm">
            {doc.versions?.map((v, i) => (
              <li key={v.id} className="flex items-start justify-between gap-3 rounded border border-stone-200 bg-white px-3 py-2">
                <div>
                  <button
                    className="text-left hover:underline"
                    onClick={() =>
                      api.download(doc.id, v.id, v.original_filename).catch((e) => setError(e.message))
                    }
                  >
                    v{i + 1} {v.original_filename}
                  </button>
                  <p className="text-xs text-stone-500">
                    {v.uploaded_by_name} · {formatWhen(v.uploaded_at)} · {v.checksum_sha256.slice(0, 12)}…
                  </p>
                </div>
                {me.role === "staff" && (
                  <button
                    disabled={busy}
                    className="shrink-0 text-xs text-red-700 hover:underline"
                    onClick={() => {
                      if (!window.confirm(`Delete file ${v.original_filename}?`)) return;
                      run(() => api.deleteVersion(doc.id, v.id));
                    }}
                  >
                    Delete file
                  </button>
                )}
              </li>
            ))}
            {!doc.versions?.length && <li className="text-stone-500">No files yet.</li>}
          </ul>
        </div>
      </div>

      <div className="lg:col-span-2">
        <h2 className="font-medium">Audit trail</h2>
        <ol className="relative mt-4 border-l border-stone-300 pl-4">
          {audit.map((e) => (
            <li key={e.id} className="mb-4">
              <p className="text-sm">{e.display_text}</p>
              <p className="font-mono text-xs text-stone-500">
                {e.actor} ({e.actor_role})
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
