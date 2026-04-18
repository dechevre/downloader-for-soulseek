import "./TrackCard.css";

import React, { useState } from "react";
import type { SearchResult, RankedCandidate } from "./App";

type TrackCardProps = {
    result: SearchResult;
    onSelectCandidate: (candidate: RankedCandidate | null) => void;
    selectedCandidate: RankedCandidate | null;
};

function formatSize(bytes: number | null): string {
    if (bytes == null) return "?";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function formatDuration(seconds: number | null): string {
    if (seconds == null) return "?";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
}

function getFolderName(filename: string): string {
    const parts = filename.split(/[\\/]/);
    // Return the immediate parent folder, or "?" if root
    return parts.length >= 2 ? parts[parts.length - 2] : "?";
}

function getBasename(filename: string): string {
    const parts = filename.split(/[\\/]/);
    return parts[parts.length - 1];
}

export default function TrackCard({ result, onSelectCandidate, selectedCandidate }: TrackCardProps) {
    const [viewingIndex, setViewingIndex] = useState(0);
    const [expanded, setExpanded] = useState(false);

    const candidates = result.ranked_candidates ?? [];
    const total = candidates.length;
    const viewing = candidates[viewingIndex] ?? null;

    const viewingIsSelected =
        selectedCandidate !== null &&
        viewing !== null &&
        selectedCandidate.filename === viewing.filename &&
        selectedCandidate.username === viewing.username;

    function handlePrev() {
        setViewingIndex(i => (i - 1 + total) % total);
    }

    function handleNext() {
        setViewingIndex(i => (i + 1) % total);
    }

    function handleCheckbox() {
        if (viewingIsSelected) {
            onSelectCandidate(null);
        } else {
            onSelectCandidate(viewing);
        }
    }

    if (result.status !== "found" || total === 0 || !viewing) {
        return null;
    }

    const ext = (viewing.extension ?? "?").toUpperCase();
    const bitrate = viewing.bitrate != null ? `${viewing.bitrate} kbps` : "? kbps";
    const size = formatSize(viewing.size);
    const folder = getFolderName(viewing.filename);
    const basename = getBasename(viewing.filename);
    const duration = formatDuration(viewing.length);

    return (
        <div className="track-card">
            <div className="candidate-summary">
                <input
                    type="checkbox"
                    className="candidate-checkbox"
                    checked={viewingIsSelected}
                    onChange={handleCheckbox}
                    title={viewingIsSelected ? "Deselect this candidate" : "Select for download"}
                />

                <span className="candidate-ext">{ext}</span>
                <span className="candidate-bitrate">{bitrate}</span>
                <span className="candidate-size">{size}</span>
                <span className="candidate-duration">{duration}</span>
                <span className="candidate-folder" title={viewing.filename}>{folder}</span>

                <div className="candidate-nav">
                    <button className="nav-btn" onClick={handlePrev} disabled={total <= 1}>◀</button>
                    <span className="candidate-counter">{viewingIndex + 1} / {total}</span>
                    <button className="nav-btn" onClick={handleNext} disabled={total <= 1}>▶</button>
                </div>

                <button
                    className="expand-btn"
                    onClick={() => setExpanded(e => !e)}
                    title={expanded ? "Collapse detail" : "Expand detail"}
                >
                    {expanded ? "▲" : "▼"}
                </button>
            </div>

            {expanded && (
                <div className="candidate-detail">
                    <div className="detail-row">
                        <span className="detail-label">FILE</span>
                        <span className="detail-value detail-filename">{basename}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">PATH</span>
                        <span className="detail-value detail-path">{viewing.filename}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">USER</span>
                        <span className="detail-value">{viewing.username}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">FORMAT</span>
                        <span className="detail-value">{ext}{viewing.bitrate != null ? ` · ${viewing.bitrate} kbps` : ""}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">DURATION</span>
                        <span className="detail-value">{duration}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">SIZE</span>
                        <span className="detail-value">{size}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">SCORE</span>
                        <span className="detail-value">
                            {viewing.score}
                            {Object.entries(viewing.subscores ?? {}).map(([k, v]) => (
                                <span key={k} className="subscore"> [{k}: {v}]</span>
                            ))}
                        </span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">QUERY</span>
                        <span className="detail-value">{viewing.source_query ?? "?"}</span>
                    </div>
                    {viewing.reasons?.length > 0 && (
                        <div className="detail-row">
                            <span className="detail-label">REASONS</span>
                            <span className="detail-value detail-tags">
                                {viewing.reasons.map((r, i) => (
                                    <span key={i} className="tag tag-good">{r}</span>
                                ))}
                            </span>
                        </div>
                    )}
                    {viewing.warnings?.length > 0 && (
                        <div className="detail-row">
                            <span className="detail-label">WARNINGS</span>
                            <span className="detail-value detail-tags">
                                {viewing.warnings.map((w, i) => (
                                    <span key={i} className="tag tag-warn">{w}</span>
                                ))}
                            </span>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
