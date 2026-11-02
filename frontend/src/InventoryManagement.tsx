import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "./api";
import {
  ITEM_CAPACITY,
  STATUS_RANK,
  classCapacity,
  displayPercent,
  fillRatio,
  itemCapacity,
  statusFor,
  statusSlug,
  type StockStatus,
} from "./lib/stockStatus";
import { PageControls, ViewDialog } from "./components/ViewDialog";
import type { InventorySnapshot } from "./types";

type RegionCode = "east" | "west";
type SortKey = "name" | "category" | "quantity" | "status";

interface Resource<T> {
  state: "loading" | "ready" | "error";
  data?: T;
  error?: string;
}

interface StockRow {
  key: string;
  name: string;
  itemCode: string | null;
  classCode: string;
  className: string;
  quantity: number;
  unit: string;
  capacity: number;
  status: StockStatus;
  fill: number;
}

interface DetectionItemView {
  item_code: string;
  quantity: number;
  confidence: number;
  name: string;
  unit: string;
}

interface DetectionTrackView {
  item_code: string;
  track_id: string;
  confidence: number;
}

interface DetectionView {
  category_code: string;
  source: "image" | "video";
  items: DetectionItemView[];
  tracks: DetectionTrackView[];
}

const LOCATIONS: { region: RegionCode; label: "Bago East" | "Bago West" }[] = [
  { region: "east", label: "Bago East" },
  { region: "west", label: "Bago West" },
];

const errorText = (reason: unknown) =>
  reason instanceof Error ? reason.message : "Unexpected request failure";

function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Yangon",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function pillClass(code: string): string {
  if (code === "foods") return "cat-foods";
  if (code === "clothing") return "cat-clothes";
  if (code === "kitchenware") return "cat-kitchenware";
  if (code === "utilities") return "cat-utility";
  if (code === "fund") return "cat-fund";
  return "cat-other";
}

function toneClass(code: string): string {
  if (code === "clothing") return "tone-clothes";
  if (code === "foods") return "tone-foods";
  if (code === "kitchenware") return "tone-kitchenware";
  if (code === "utilities") return "tone-utility";
  if (code === "fund") return "tone-fund";
  return "tone-total";
}

function unitLabel(unit: string): string {
  return unit.toLowerCase() === "mmk" ? "MMK" : unit;
}

function subclassLabel(
  snapshot: InventorySnapshot | undefined,
  categoryCode: string,
  itemCode: string,
): { name: string; unit: string } {
  const item = snapshot?.classes
    .find((row) => row.code === categoryCode)
    ?.items.find((entry) => entry.code === itemCode);
  return { name: item?.name ?? itemCode, unit: item?.unit ?? "" };
}

function Glyph({ tone, compact, children }: { tone: string; compact?: boolean; children: ReactNode }) {
  return (
    <span className={`item-glyph tone-${tone}${compact ? " is-compact" : ""}`} aria-hidden="true">
      <svg viewBox="0 0 24 24">{children}</svg>
    </span>
  );
}

function TotalItemsIcon({ compact = false }: { compact?: boolean }) {
  return (
    <Glyph tone="slate" compact={compact}>
      <path d="M4 8h7v7H4zM13 8h7v7h-7zM8 15h7v5H8z" />
    </Glyph>
  );
}

function ClassGlyph({ classCode, compact = false }: { classCode: string; compact?: boolean }) {
  const tone =
    classCode === "clothing"
      ? "sky"
      : classCode === "foods"
        ? "amber"
        : classCode === "fund"
          ? "green"
          : classCode === "kitchenware"
            ? "rose"
            : "orange";
  return (
    <Glyph tone={tone} compact={compact}>
      {classCode === "clothing" && <path d="M8 7l4-3 4 3v3l3 2-2 2-1-1v7H8V13l-1 1-2-2 3-2V7z" />}
      {classCode === "foods" && <path d="M7 9h10l-1 10H8L7 9zm1-3h8l1 3H7l1-3z" />}
      {classCode === "fund" && <path d="M5 8h14v9H5zM8 8V6h8v2M9 12h6" />}
      {classCode === "kitchenware" && <path d="M6 8h12v8H6zM8 8V6h8v2M10 14h4" />}
      {classCode === "utilities" && <path d="M5 7h14v10H5zM8 7v10M12 7v10M16 7v10" />}
      {classCode !== "clothing" &&
        classCode !== "foods" &&
        classCode !== "fund" &&
        classCode !== "kitchenware" &&
        classCode !== "utilities" && <path d="M5 7h14v10H5zM8 7v10M12 7v10M16 7v10" />}
    </Glyph>
  );
}

function ItemGlyph({ itemCode, compact = false }: { itemCode: string | null; compact?: boolean }) {
  const key = itemCode ?? "fund";
  const tone =
    key.includes("longyi") || key.includes("cloth") || key === "tshirt"
      ? "sky"
      : key === "rice" || key === "oil" || key === "canned_fish"
        ? "amber"
        : "orange";
  return (
    <Glyph tone={tone} compact={compact}>
      {key === "tshirt" && <path d="M8 6l4-2 4 2 3 2-2 2h-2v8H9V10H7L5 8z" />}
      {key === "m_longyi" && <path d="M8 5h8l2 3v12H6V8zM10 5v3h4V5" />}
      {key === "f_longyi" && <path d="M9 4h6l3 4-2 2v10H8V10L6 8z" />}
      {key === "rice" && <path d="M7 9h10l-1 10H8zM8 6h8l1 3H7z" />}
      {key === "oil" && <path d="M9 3h6v3l1 2v12H8V8l1-2z" />}
      {key === "canned_fish" && <path d="M8 6h8v12H8zM8 6c0-1 8-1 8 0M8 18c0 1 8 1 8 0" />}
      {key === "blanket" && <path d="M5 7h14v10H5zM8 7v10M12 7v10M16 7v10" />}
      {key === "soap" && <path d="M7 9h10v8H7zM9 9V7h6v2" />}
      {key === "water_dipper" && <path d="M10 4c2 0 3 2 3 4v4l4 8H7l4-8V8c0-2 1-4 3-4z" />}
      {key === "spoon" && <path d="M10 4c2 2 2 4 0 6l1 8h2l1-8c-2-2-2-4 0-6" />}
      {key === "mug" && <path d="M7 7h8v8a3 3 0 0 1-3 3H10a3 3 0 0 1-3-3zM15 9h2a2 2 0 0 1 0 4h-2" />}
      {key === "box" && <path d="M4 8l8-3 8 3-8 3zM4 8v8l8 3V11M20 8v8l-8 3" />}
      {key === "towel" && <path d="M7 4h10v16H7zM9 4v16" />}
      {key === "plate" && <path d="M5 12a7 7 0 1 0 14 0 7 7 0 0 0-14 0zm3 0a4 4 0 1 0 8 0" />}
      {key === "bednet" && <path d="M4 10h16v6H4zM6 10V7h4M18 10V7h-4M4 16v2M20 16v2" />}
      {key === "knife" && <path d="M14 4l4 2-8 10H6l8-12zM8 16l2 4" />}
      {key === "bowl" && <path d="M5 10h14c0 5-3 8-7 8s-7-3-7-8z" />}
      {key === "pot" && <path d="M6 10h12v7H6zM4 10h16M9 10V7M15 10V7" />}
      {key === "fund" && <path d="M5 8h14v9H5zM8 8V6h8v2M9 12h6" />}
    </Glyph>
  );
}

function CubeIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3 4 7.5 12 12l8-4.5L12 3z" />
      <path d="M4 7.5V16.5L12 21l8-4.5V7.5" />
      <path d="M12 12v9" />
    </svg>
  );
}

export default function InventoryManagement() {
  const [region, setRegion] = useState<RegionCode>("east");
  const [resource, setResource] = useState<Resource<InventorySnapshot>>({ state: "loading" });
  const [classFilter, setClassFilter] = useState<string>("all");
  const [status, setStatus] = useState<StockStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [showAllUpdates, setShowAllUpdates] = useState(false);
  const [updatesPage, setUpdatesPage] = useState(0);
  const [restockOpen, setRestockOpen] = useState(false);
  const [searchSlot, setSearchSlot] = useState<HTMLElement | null>(null);
  const [restockPage, setRestockPage] = useState(0);
  const [addOpen, setAddOpen] = useState(false);
  const [addMode, setAddMode] = useState<"detect" | "manual" | null>(null);
  const [saving, setSaving] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [scanPhoto, setScanPhoto] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [manualClass, setManualClass] = useState("");
  const [manualItem, setManualItem] = useState("");
  const [manualQuantity, setManualQuantity] = useState("");
  const [detectClass, setDetectClass] = useState("");
  const [detection, setDetection] = useState<DetectionView | null>(null);
  const [formError, setFormError] = useState("");
  const [catalogPanel, setCatalogPanel] = useState<"none" | "class" | "subclass">("none");
  const [newClassCode, setNewClassCode] = useState("");
  const [newClassName, setNewClassName] = useState("");
  const [newClassMode, setNewClassMode] = useState<"scan_or_manual" | "manual_only">("scan_or_manual");
  const [newSubclassClass, setNewSubclassClass] = useState("");
  const [newSubclassCode, setNewSubclassCode] = useState("");
  const [newSubclassName, setNewSubclassName] = useState("");
  const [newSubclassUnit, setNewSubclassUnit] = useState("piece");
  const galleryInputRef = useRef<HTMLInputElement | null>(null);
  const cameraVideoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const regionRef = useRef(region);
  const snapshotRef = useRef<InventorySnapshot | undefined>(undefined);
  const mounted = useRef(true);
  regionRef.current = region;
  snapshotRef.current = resource.data;

  const stopCamera = useCallback(() => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    if (cameraVideoRef.current) {
      cameraVideoRef.current.srcObject = null;
    }
    setCameraOpen(false);
    setCameraError("");
  }, []);

  const clearScanPhoto = useCallback(() => {
    setScanPhoto(null);
    setPreviewUrl("");
  }, []);

  const closeAdd = useCallback(() => {
    stopCamera();
    clearScanPhoto();
    setAddOpen(false);
    setAddMode(null);
    setDetecting(false);
    setFormError("");
    setManualClass("");
    setManualItem("");
    setManualQuantity("");
    setDetectClass("");
    setDetection(null);
    setCatalogPanel("none");
    setNewClassCode("");
    setNewClassName("");
    setNewClassMode("scan_or_manual");
    setNewSubclassClass("");
    setNewSubclassCode("");
    setNewSubclassName("");
    setNewSubclassUnit("piece");
  }, [clearScanPhoto, stopCamera]);

  useEffect(() => {
    if (!cameraOpen) return;
    let cancelled = false;
    let stream: MediaStream | null = null;
    void (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setCameraError("This browser cannot use the camera. Upload a photo instead.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        cameraStreamRef.current = stream;
        const video = cameraVideoRef.current;
        if (video) {
          video.srcObject = stream;
          await video.play();
        }
      } catch {
        if (!cancelled) {
          setCameraError("Could not open the camera. Allow access in the browser or upload a photo.");
        }
      }
    })();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    };
  }, [cameraOpen]);

  const captureFromCamera = () => {
    const video = cameraVideoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        setScanPhoto(blob);
        setDetection(null);
        setFormError("");
        stopCamera();
      },
      "image/jpeg",
      0.92,
    );
  };

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!scanPhoto) {
      setPreviewUrl("");
      return;
    }
    const url = URL.createObjectURL(scanPhoto);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [scanPhoto]);

  useEffect(() => {
    if (!addOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAdd();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [addOpen, closeAdd]);

  useEffect(() => {
    let active = true;
    setResource({ state: "loading" });
    api.inventory(region)
      .then((data) => {
        if (active) setResource({ state: "ready", data });
      })
      .catch((reason: unknown) => {
        if (active) setResource({ state: "error", error: errorText(reason) });
      });
    return () => {
      active = false;
    };
  }, [region]);

  const classes = resource.data?.classes ?? [];

  const rows = useMemo<StockRow[]>(() => {
    return classes.flatMap((row) =>
      row.items.map((item) => {
        const capacity = itemCapacity(row.code, item);
        return {
          key: `${row.code}:${item.code ?? "fund"}`,
          name: item.name,
          itemCode: item.code,
          classCode: row.code,
          className: row.name,
          quantity: item.quantity,
          unit: item.unit,
          capacity,
          status: statusFor(item.quantity, capacity),
          fill: displayPercent(item.quantity, capacity),
        };
      }),
    );
  }, [classes]);

  useEffect(() => {
    setSearchSlot(document.getElementById("inventory-search-slot"));
  }, []);

  const visible = useMemo(() => {
    const search = query.trim().toLowerCase();
    const filtered = rows.filter((item) => {
      if (classFilter !== "all" && item.classCode !== classFilter) return false;
      if (status !== "all" && item.status !== status) return false;
      if (!search) return true;
      return `${item.name} ${item.className} ${item.unit}`.toLowerCase().includes(search);
    });
    if (!sortKey) return filtered;
    const statusRank = STATUS_RANK;
    return [...filtered].sort((left, right) => {
      const dir = sortAsc ? 1 : -1;
      if (sortKey === "quantity") return (left.quantity - right.quantity) * dir;
      if (sortKey === "status") return (statusRank[left.status] - statusRank[right.status]) * dir;
      if (sortKey === "category") return left.className.localeCompare(right.className) * dir;
      return left.name.localeCompare(right.name) * dir;
    });
  }, [rows, classFilter, status, query, sortKey, sortAsc]);

  const movements = resource.data?.movements ?? [];
  const shownUpdates = movements.slice(0, 4);
  const updatePages = Math.max(1, Math.ceil(movements.length / 6));
  const updateSlice = movements.slice(updatesPage * 6, updatesPage * 6 + 6);
  const goods = classes.filter((row) => row.code !== "fund");
  const totalQuantity = goods.reduce((sum, row) => sum + row.quantity, 0);
  const totalCapacity =
    goods.reduce((sum, row) => sum + row.items.length * ITEM_CAPACITY, 0) || ITEM_CAPACITY * 3;
  const totalStatus = statusFor(totalQuantity, totalCapacity);
  const totalFill = displayPercent(totalQuantity, totalCapacity);
  const restock = [
    ...(fillRatio(totalQuantity, totalCapacity) < 30
      ? [{ key: "total", name: "Total items", classCode: "total", status: totalStatus, fill: totalFill }]
      : []),
    ...rows
      .filter((row) => fillRatio(row.quantity, itemCapacity(row.classCode)) < 30)
      .map((row) => ({
        key: row.key,
        name: row.name,
        classCode: row.classCode,
        status: row.status,
        fill: row.fill,
      })),
  ];
  const manualSelected = classes.find((row) => row.code === manualClass);
  const manualIsFund = manualSelected?.code === "fund" || manualSelected?.entry_mode === "manual_only";
  const detectClasses = classes.filter((row) => row.code !== "fund" && row.entry_mode !== "manual_only");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((current) => !current);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const applySnapshot = (data: InventorySnapshot, requested: RegionCode) => {
    if (regionRef.current === requested) setResource({ state: "ready", data });
  };

  const applyLocations = (locations: InventorySnapshot[]) => {
    const current = locations.find((row) => row.region === regionRef.current);
    if (current) setResource({ state: "ready", data: current });
  };

  const submitNewClass = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setFormError("");
    setSaving(true);
    try {
      const result = await api.createInventoryCategory({
        code: newClassCode.trim().toLowerCase(),
        name: newClassName.trim(),
        entry_mode: newClassMode,
      });
      applyLocations(result.locations);
      setCatalogPanel("none");
      setNewClassCode("");
      setNewClassName("");
    } catch (reason) {
      setFormError(errorText(reason));
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const submitNewSubclass = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setFormError("");
    setSaving(true);
    try {
      const result = await api.createInventoryItemType(newSubclassClass, {
        code: newSubclassCode.trim().toLowerCase(),
        name: newSubclassName.trim(),
        unit: newSubclassUnit.trim(),
      });
      applyLocations(result.locations);
      setCatalogPanel("none");
      setNewSubclassCode("");
      setNewSubclassName("");
      setNewSubclassUnit("piece");
    } catch (reason) {
      setFormError(errorText(reason));
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const submitManual = async (event: FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setFormError("");
    if (!manualSelected) {
      setFormError("Choose a class.");
      return;
    }
    if (!manualIsFund && !manualItem) {
      setFormError("Choose a subclass.");
      return;
    }
    const quantity = Number(manualQuantity);
    if (!Number.isFinite(quantity) || quantity <= 0) {
      setFormError("Enter a quantity greater than zero.");
      return;
    }
    const cap = classCapacity(manualSelected);
    if (manualSelected.quantity + quantity > cap) {
      setFormError(`${manualSelected.name} is limited to ${cap.toLocaleString()}.`);
      return;
    }
    const requested = region;
    setSaving(true);
    try {
      const saved = await api.addInventory(requested, {
        category_code: manualSelected.code,
        item_code: manualIsFund ? null : manualItem,
        quantity,
        entry_mode: "manual",
        direction: "in",
      });
      applySnapshot(saved, requested);
      closeAdd();
    } catch (reason) {
      setFormError(errorText(reason));
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const runDetect = async () => {
    setFormError("");
    if (!detectClass) {
      setFormError("Choose a class.");
      return;
    }
    if (!scanPhoto) {
      setFormError("Take or upload a photo before detecting.");
      return;
    }
    setDetecting(true);
    setDetection(null);
    try {
      const result = await api.detectInventory(detectClass, scanPhoto);
      const items = result.items.map((item) => {
        const label = subclassLabel(snapshotRef.current, result.category_code, item.item_code);
        return {
          item_code: item.item_code,
          quantity: 1,
          confidence: item.confidence,
          name: label.name,
          unit: label.unit,
        };
      });
      if (!mounted.current) return;
      setDetection({
        category_code: result.category_code,
        source: "image",
        items,
        tracks: result.tracks ?? [],
      });
    } catch (reason) {
      if (mounted.current) {
        setDetection(null);
        setFormError(errorText(reason));
      }
    } finally {
      if (mounted.current) setDetecting(false);
    }
  };

  const updateDetectedQuantity = (itemCode: string, raw: string) => {
    const quantity = raw.trim() === "" ? 0 : Number(raw);
    setDetection((current) => {
      if (!current) return current;
      return {
        ...current,
        items: current.items.map((item) =>
          item.item_code === itemCode
            ? { ...item, quantity: Number.isFinite(quantity) ? quantity : 0 }
            : item,
        ),
      };
    });
  };

  const confirmDetection = async () => {
    if (!detection || detection.items.length === 0 || saving) return;
    setFormError("");
    const selected = classes.find((row) => row.code === detection.category_code);
    for (const item of detection.items) {
      if (!Number.isFinite(item.quantity) || item.quantity <= 0) {
        setFormError(`Enter a quantity greater than zero for ${item.name}.`);
        return;
      }
      const stock = selected?.items.find((row) => row.code === item.item_code);
      const cap = itemCapacity(detection.category_code, stock);
      if ((stock?.quantity ?? 0) + item.quantity > cap) {
        setFormError(`${item.name} is limited to ${cap.toLocaleString()}.`);
        return;
      }
    }
    const requested = region;
    setSaving(true);
    try {
      const saved = await api.confirmDetection(requested, {
        category_code: detection.category_code,
        source: detection.source,
        items: detection.items.map((item) => ({
          item_code: item.item_code,
          quantity: item.quantity,
          confidence: item.confidence,
        })),
        tracks: detection.tracks,
      });
      applySnapshot(saved, requested);
      closeAdd();
    } catch (reason) {
      setFormError(errorText(reason));
    } finally {
      if (mounted.current) setSaving(false);
    }
  };

  const searchBar = (
    <label className="inv-search">
      <span className="sr-only">Search items, classes, or locations</span>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="6.5" />
        <path d="M16 16.5 20 20.5" />
      </svg>
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search items, classes, or locations..."
        type="search"
      />
    </label>
  );

  return (
    <main className="inventory">
      {searchSlot ? createPortal(searchBar, searchSlot) : null}

      {resource.state === "loading" && <p className="state">Loading inventory…</p>}
      {resource.state === "error" && (
        <p className="state error" role="alert">Inventory unavailable: {resource.error}</p>
      )}

      {resource.state === "ready" && (
        <div className="inv-stats-row">
        <section className="inv-stats" aria-label="Inventory totals">
          <article className="stat-card tone-total">
            <div>
              <p>
                <span className="stat-icon" aria-hidden="true"><TotalItemsIcon /></span>
                Total items
              </p>
              <strong>{totalQuantity.toLocaleString()}</strong>
              <small>{totalStatus} · {totalFill}%</small>
            </div>
          </article>
          {classes.map((row) => {
            const capacity = classCapacity(row);
            const cardStatus = statusFor(row.quantity, capacity);
            const fill = displayPercent(row.quantity, capacity);
            return (
              <article key={row.code} className={`stat-card ${toneClass(row.code)}`}>
                <div>
                  <p>
                    <span className="stat-icon" aria-hidden="true">
                      <ClassGlyph classCode={row.code} />
                    </span>
                    {row.name}
                  </p>
                  <strong>{row.quantity.toLocaleString()}</strong>
                  <small>{cardStatus} · {fill}%</small>
                </div>
              </article>
            );
          })}
        </section>
        <div className="catalog-actions inv-stats-actions">
          <button
            type="button"
            className="add-launch"
            onClick={() => setCatalogPanel("class")}
          >
            New class
          </button>
          <button
            type="button"
            className="add-launch"
            onClick={() => setCatalogPanel("subclass")}
          >
            New subclass
          </button>
        </div>
        </div>
      )}

      <div className="inv-layout">
        <section className="inv-table-card">
          <div className="inv-card-bar">
            <div className="inv-filters">
              <label>
                Location
                <select
                  value={region}
                  onChange={(event) => {
                    setRegion(event.target.value as RegionCode);
                    setResource({ state: "loading" });
                    setShowAllUpdates(false);
                  }}
                >
                  {LOCATIONS.map((place) => (
                    <option key={place.region} value={place.region}>{place.label}</option>
                  ))}
                </select>
              </label>
              <label>
                Class
                <select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}>
                  <option value="all">All Classes</option>
                  {classes.map((row) => (
                    <option key={row.code} value={row.code}>{row.name}</option>
                  ))}
                </select>
              </label>
              <label>
                Status
                <select
                  value={status}
                  onChange={(event) => setStatus(event.target.value as StockStatus | "all")}
                >
                  <option value="all">All Status</option>
                  <option value="Out of Stock">Out of Stock</option>
                  <option value="Critical">Critical</option>
                  <option value="Low Stock">Low Stock</option>
                  <option value="In Stock">In Stock</option>
                  <option value="Full">Full</option>
                </select>
              </label>
            </div>
            <div className="catalog-actions inv-card-actions">
              <button
                type="button"
                className="add-launch"
                onClick={() => setAddOpen(true)}
                disabled={resource.state !== "ready"}
              >
                + Add Item
              </button>
            </div>
          </div>

          <div className="inv-table" role="table" aria-label="Inventory items">
            <div className="inv-row header" role="row">
              <span role="columnheader">#</span>
              <span role="columnheader">
                <button type="button" onClick={() => toggleSort("name")}>Item</button>
              </span>
              <span role="columnheader">
                <button type="button" onClick={() => toggleSort("category")}>Class</button>
              </span>
              <span role="columnheader">
                <button type="button" onClick={() => toggleSort("quantity")}>Quantity</button>
              </span>
              <span role="columnheader">
                <button type="button" onClick={() => toggleSort("status")}>Status</button>
              </span>
            </div>
            {resource.state === "ready" && visible.length === 0 && (
              <p className="inv-empty">No items match these filters.</p>
            )}
            {visible.map((item, index) => (
              <div className="inv-row" role="row" key={item.key}>
                <span>{index + 1}</span>
                <span className="item-name">
                  <ItemGlyph itemCode={item.itemCode} />
                  {item.name}
                </span>
                <span className="class-cell">
                  <ClassGlyph classCode={item.classCode} compact />
                  <em className={`cat-pill ${pillClass(item.classCode)}`}>{item.className}</em>
                </span>
                <span>{item.quantity.toLocaleString()} {unitLabel(item.unit)}</span>
                <span>
                  <em
                    className={`stock-pill stock-${statusSlug(item.status)}`}
                    title={`${item.name} is ${item.fill}% of the ${item.capacity.toLocaleString()} ${item.unit} subclass limit`}
                  >
                    {item.status}
                  </em>
                </span>
              </div>
            ))}
          </div>
        </section>

        <aside className="inv-rail">
          <section className="rail-card alert-card">
            <header>
              <h2>Restock</h2>
              <b>{restock.length}</b>
            </header>
            {restock.length === 0 && <p className="rail-empty">No class is below 30%.</p>}
            <ul>
              {restock.slice(0, 4).map((item) => (
                <li key={item.key}>
                  {item.classCode === "total"
                    ? <TotalItemsIcon compact />
                    : <ClassGlyph classCode={item.classCode} compact />}
                  <div>
                    <strong>{item.name}</strong>
                    <small>{item.status} · {item.fill}% of capacity</small>
                  </div>
                </li>
              ))}
            </ul>
            {restock.length > 4 ? (
              <button type="button" className="text-link" onClick={() => { setRestockPage(0); setRestockOpen(true); }}>
                View restock
              </button>
            ) : null}
          </section>
          <section className="rail-card">
            <header>
              <h2>Recent Stock Updates</h2>
              {movements.length > 4 && (
                <button
                  type="button"
                  className="text-link"
                  onClick={() => {
                    setUpdatesPage(0);
                    setShowAllUpdates(true);
                  }}
                >
                  View All
                </button>
              )}
            </header>
            {resource.state === "loading" && <p className="rail-empty">Loading stock updates…</p>}
            {resource.state === "error" && <p className="rail-empty">Stock updates are unavailable.</p>}
            {resource.state === "ready" && movements.length === 0 && (
              <p className="rail-empty">No stock updates for this location.</p>
            )}
            <ul className="update-list">
              {shownUpdates.map((update) => {
                const signed = update.direction === "out" ? -update.quantity : update.quantity;
                const positive = update.direction === "in";
                const change = `${signed > 0 ? "+" : ""}${signed.toLocaleString()} ${unitLabel(update.unit)}`;
                return (
                  <li key={update.id}>
                    <span className={positive ? "up" : "down"} aria-hidden="true">{positive ? "+" : "−"}</span>
                    <div>
                      <strong>{update.name}</strong>
                      <em className={positive ? "up" : "down"}>{change}</em>
                      <small>
                        {update.entry_mode === "scan" ? "Scan · " : ""}
                        {formatWhen(update.created_at)}
                      </small>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        </aside>
      </div>

      {addOpen && (
        <div
          className="inv-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeAdd();
          }}
        >
          <div
            className={addMode === null ? "inv-modal hf-modal" : "inv-modal is-single hf-modal"}
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-item-title"
          >
            <header className="modal-head">
              <div>
                <h2 id="add-item-title">
                  <span className="inv-mark" aria-hidden="true"><CubeIcon /></span>
                  Add Item
                </h2>
                <p>Choose how you want to add the item to inventory</p>
              </div>
              <button type="button" className="modal-close" aria-label="Close" onClick={closeAdd}>
                ×
              </button>
            </header>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            {addMode === null && (
              <div className="add-grid">
                <button type="button" className="add-card add-choice" onClick={() => setAddMode("detect")}>
                  <span className="choice-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d="M4 8V5h3M20 8V5h-3M4 16v3h3M20 16v3h-3M12 9v6M9 12h6" /></svg>
                  </span>
                  <h3>Detect Object</h3>
                  <p>Take or upload a photo of clothing, foods, kitchenware, or utilities.</p>
                </button>
                <button type="button" className="add-card add-choice" onClick={() => setAddMode("manual")}>
                  <span className="choice-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24"><path d="M7 3h7l5 5v13H7z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>
                  </span>
                  <h3>Manual Add</h3>
                  <p>Type the class, subclass, and quantity. Fund is only here.</p>
                </button>
              </div>
            )}
            {addMode !== null && (
            <div className="add-grid single">
              <section className="add-card">
                <button type="button" className="text-link" onClick={() => { clearScanPhoto(); setAddMode(null); setFormError(""); }}>
                  Choose another way
                </button>
                {addMode === "detect" && (
                <>
                <h3>Detect Object</h3>
                <p>Take a photo with your camera or upload one from your device. Every item is counted. Stock is saved only after you confirm.</p>
                <label>
                  Class
                  <select
                    value={detectClass}
                    onChange={(event) => {
                      setDetectClass(event.target.value);
                      clearScanPhoto();
                      setDetection(null);
                      setFormError("");
                    }}
                  >
                    <option value="">Select class</option>
                    {detectClasses.map((row) => (
                      <option key={row.code} value={row.code}>{row.name}</option>
                    ))}
                  </select>
                </label>
                <div className="detect-stage">
                  {cameraOpen ? (
                    <div className="camera-live">
                      <video ref={cameraVideoRef} playsInline muted className="camera-preview" />
                      {cameraError ? <p className="camera-note" role="alert">{cameraError}</p> : null}
                      <div className="camera-live-actions">
                        <button type="button" className="detect-secondary" onClick={stopCamera}>
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="detect-primary"
                          onClick={captureFromCamera}
                          disabled={Boolean(cameraError)}
                        >
                          Capture photo
                        </button>
                      </div>
                    </div>
                  ) : previewUrl ? (
                    <img src={previewUrl} alt="Photo to scan" />
                  ) : (
                    <div className="detect-art" aria-hidden="true">
                      <svg viewBox="0 0 120 72">
                        <rect x="8" y="8" width="104" height="56" rx="10" />
                        <path d="M18 24V16h8M102 24V16h-8M18 48v8h8M102 48v8h-8" />
                        <rect x="46" y="24" width="28" height="24" rx="4" />
                      </svg>
                    </div>
                  )}
                </div>
                <input
                  ref={galleryInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) {
                      setScanPhoto(file);
                      setDetection(null);
                      setFormError("");
                    }
                    event.target.value = "";
                  }}
                />
                {detection && detectClass === detection.category_code && detection.items.length > 0 && (
                  <div className="detect-result">
                    {detection.items.map((item) => (
                      <label className="detect-qty" key={item.item_code}>
                        <span className="detect-result-label">{item.name}</span>
                        <span className="detect-qty-field">
                          <input
                            type="number"
                            min="0"
                            step="any"
                            value={item.quantity || ""}
                            aria-label={`${item.name} quantity`}
                            onChange={(event) => updateDetectedQuantity(item.item_code, event.target.value)}
                          />
                          <span className="detect-unit">{item.unit ? unitLabel(item.unit) : "qty"}</span>
                        </span>
                      </label>
                    ))}
                    <button type="button" className="detect-save" onClick={() => void confirmDetection()} disabled={saving || detecting}>
                      {saving ? "Saving…" : detection.items.length > 1 ? "Save detected items" : "Save detected item"}
                    </button>
                  </div>
                )}
                <div className="detect-actions">
                  <button
                    type="button"
                    className="detect-primary"
                    onClick={() => {
                      setCameraError("");
                      setCameraOpen(true);
                    }}
                    disabled={cameraOpen || detecting}
                  >
                    {previewUrl ? "Retake photo" : "Take photo"}
                  </button>
                  <button
                    type="button"
                    className="detect-secondary"
                    onClick={() => galleryInputRef.current?.click()}
                    disabled={cameraOpen || detecting}
                  >
                    {previewUrl ? "Choose another file" : "Upload photo"}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => void runDetect()}
                  disabled={detecting || saving || !scanPhoto || !detectClass}
                >
                  {detecting ? "Detecting…" : "Detect Object"}
                </button>
                </>
                )}
                {addMode === "manual" && (
                <>
                <h3>Manual Add</h3>
                <p>Enter a class and quantity. Fund has no subclass.</p>
                <form onSubmit={(event) => void submitManual(event)} noValidate>
                  <label>
                    Class
                    <select
                      value={manualClass}
                      onChange={(event) => {
                        setManualClass(event.target.value);
                        setManualItem("");
                      }}
                    >
                      <option value="">Select class</option>
                      {classes.map((row) => (
                        <option key={row.code} value={row.code}>{row.name}</option>
                      ))}
                    </select>
                  </label>
                  {manualSelected && !manualIsFund && (
                    <label>
                      Subclass
                      <select value={manualItem} onChange={(event) => setManualItem(event.target.value)}>
                        <option value="">Select subclass</option>
                        {manualSelected.items.filter((item) => item.code).map((item) => (
                          <option key={item.code} value={item.code ?? ""}>{item.name}</option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label>
                    Quantity
                    <input
                      type="number"
                      min="0"
                      step="any"
                      value={manualQuantity}
                      onChange={(event) => setManualQuantity(event.target.value)}
                      placeholder="Enter quantity"
                    />
                  </label>
                  <button type="submit" disabled={saving}>
                    {saving ? "Saving…" : "Add Item"}
                  </button>
                </form>
                </>
                )}
              </section>
            </div>
            )}
          </div>
        </div>
      )}
      <ViewDialog title="Stock updates" open={showAllUpdates} onClose={() => setShowAllUpdates(false)}>
        <ul className="update-list">
          {updateSlice.map((update) => (
            <li key={update.id}>
              <strong>{update.name}</strong>
              <span>
                {update.direction === "out" ? "−" : "+"}
                {update.quantity.toLocaleString()} {unitLabel(update.unit)}
              </span>
            </li>
          ))}
        </ul>
        <PageControls page={updatesPage} pages={updatePages} onPage={setUpdatesPage} />
      </ViewDialog>
      <ViewDialog title="Restock" open={restockOpen} onClose={() => setRestockOpen(false)}>
        <ul className="home-list">
          {restock.slice(restockPage * 6, restockPage * 6 + 6).map((item) => (
            <li key={item.key}>
              <strong>{item.name}</strong>
              <span>{item.status} · {item.fill}%</span>
            </li>
          ))}
        </ul>
        <PageControls page={restockPage} pages={Math.max(1, Math.ceil(restock.length / 6))} onPage={setRestockPage} />
      </ViewDialog>
      <ViewDialog title="New class" open={catalogPanel === "class"} onClose={() => setCatalogPanel("none")}>
        <form className="catalog-form" onSubmit={(event) => void submitNewClass(event)} noValidate>
          <label>
            Class code
            <input value={newClassCode} onChange={(event) => setNewClassCode(event.target.value)} placeholder="e.g. medical" />
          </label>
          <label>
            Display name
            <input value={newClassName} onChange={(event) => setNewClassName(event.target.value)} placeholder="Medical" />
          </label>
          <label>
            Entry mode
            <select
              value={newClassMode}
              onChange={(event) => setNewClassMode(event.target.value as "scan_or_manual" | "manual_only")}
            >
              <option value="scan_or_manual">Scan or manual</option>
              <option value="manual_only">Manual only</option>
            </select>
          </label>
          <button type="submit" disabled={saving}>{saving ? "Saving…" : "Create class"}</button>
        </form>
      </ViewDialog>
      <ViewDialog title="New subclass" open={catalogPanel === "subclass"} onClose={() => setCatalogPanel("none")}>
        <form className="catalog-form" onSubmit={(event) => void submitNewSubclass(event)} noValidate>
          <label>
            Class
            <select value={newSubclassClass} onChange={(event) => setNewSubclassClass(event.target.value)}>
              <option value="">Select class</option>
              {classes
                .filter((row) => row.code !== "fund" && row.entry_mode !== "manual_only")
                .map((row) => (
                  <option key={row.code} value={row.code}>{row.name}</option>
                ))}
            </select>
          </label>
          <label>
            Subclass code
            <input value={newSubclassCode} onChange={(event) => setNewSubclassCode(event.target.value)} placeholder="e.g. bandage" />
          </label>
          <label>
            Display name
            <input value={newSubclassName} onChange={(event) => setNewSubclassName(event.target.value)} placeholder="Bandage" />
          </label>
          <label>
            Unit
            <input value={newSubclassUnit} onChange={(event) => setNewSubclassUnit(event.target.value)} placeholder="piece" />
          </label>
          <button type="submit" disabled={saving}>{saving ? "Saving…" : "Create subclass"}</button>
        </form>
      </ViewDialog>
    </main>
  );
}
