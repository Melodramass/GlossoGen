"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/shared/lib/cn";

/** Panel width classes, spelled out in full so Tailwind sees each one. */
const MODAL_WIDTH_CLASS = {
  sm: "max-w-sm",
  md: "max-w-md",
  "2xl": "max-w-2xl",
  "3xl": "max-w-3xl",
  "5xl": "max-w-5xl",
} as const;

export type ModalWidth = keyof typeof MODAL_WIDTH_CLASS;

interface OpenModal {
  /** The modal's latest `onClose`, updated on every render. */
  close: { current: () => void };
}

/**
 * Open modals, oldest first. One `keydown` listener on `window` serves all of
 * them and closes the last one, so which modal answers Escape never depends on
 * the order listeners were added or on a modal unmounting mid-dispatch.
 */
const openModals: OpenModal[] = [];

function closeTopmostOnEscape(event: KeyboardEvent) {
  const topmost = openModals[openModals.length - 1];
  if (event.key === "Escape" && topmost !== undefined) {
    topmost.close.current();
  }
}

function openModal(modal: OpenModal) {
  if (openModals.length === 0) {
    window.addEventListener("keydown", closeTopmostOnEscape);
  }
  openModals.push(modal);
}

function closeModal(modal: OpenModal) {
  openModals.splice(openModals.indexOf(modal), 1);
  if (openModals.length === 0) {
    window.removeEventListener("keydown", closeTopmostOnEscape);
  }
}

interface ModalProps {
  /** Accessible name of the dialog. */
  label: string;
  width: ModalWidth;
  /** Layout inside the panel: flex direction, max height, padding. */
  panelClassName: string;
  /** Lets something outside the modal find the panel, as the guided tour does. */
  panelId: string | null;
  onClose: () => void;
  children: React.ReactNode;
}

/**
 * A dialog over a dimmed, scrollable backdrop, rendered into document.body.
 *
 * Escape and a click on the backdrop call `onClose`; a click inside the panel
 * does not. Escape is read on `window`, so a field inside the panel that
 * handles Escape itself and stops its propagation keeps the modal open. Of
 * several open modals only the most recently opened answers Escape.
 *
 * On open, focus moves to the panel unless a child already took it (an
 * `autoFocus` field); on close it returns to the element that had it before.
 */
export function Modal({ label, width, panelClassName, panelId, onClose, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  // Read during the first render, before any `autoFocus` child takes focus.
  const [focusBeforeOpen] = useState<Element | null>(() => document.activeElement);
  const close = useRef(onClose);
  const [modal] = useState<OpenModal>(() => ({ close }));

  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  useEffect(() => {
    openModal(modal);
    return () => closeModal(modal);
  }, [modal]);

  useEffect(() => {
    const panel = panelRef.current;
    if (panel === null) {
      return;
    }
    if (!panel.contains(document.activeElement)) {
      panel.focus({ preventScroll: true });
    }
    return () => {
      // On a real unmount the panel has already left the DOM. StrictMode's
      // simulated one leaves it in place, and restoring focus then would pull
      // it off an `autoFocus` field for good.
      if (panel.isConnected) {
        return;
      }
      if (focusBeforeOpen instanceof HTMLElement && focusBeforeOpen.isConnected) {
        focusBeforeOpen.focus({ preventScroll: true });
      }
    };
  }, [focusBeforeOpen]);

  return createPortal(
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-black/50"
      onClick={onClose}
      role="presentation"
    >
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          ref={panelRef}
          id={panelId ?? undefined}
          role="dialog"
          aria-modal="true"
          aria-label={label}
          tabIndex={-1}
          className={cn(
            "w-full rounded-xl border border-border bg-background shadow-xl outline-none",
            MODAL_WIDTH_CLASS[width],
            panelClassName
          )}
          onClick={event => event.stopPropagation()}
        >
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
}
