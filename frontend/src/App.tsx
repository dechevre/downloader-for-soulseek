import React, { useState } from "react";
import TrackCard from "./TrackCard"
import "./App.css"

export type Track = {
    artist: string;
    title: string;
    duration: number | null,
    year?: number | null, // Duration in seconds
}

export type RankedCandidate = {
    filename: string;
    username: string;
    size: number | null;
    size_mb?: number | null;
    bitrate: number | null;
    length: number | null;
    extension: string | null;
    source_query: string | null;
    raw: Record<string, unknown>;

    score: number;
    subscores: Record<string, number>;
    reasons: string[];
    warnings: string[];
}

export type SearchResultTrack = {
    artist: string;
    title: string;
    duration: number | null;
    year: number | null;
    display_name: string;
};

export type SearchQueries = {
    exact: string | null;
    fallback: string | null;
    used_fallback: boolean;
};

export type SearchCounts = {
    exact_candidates: number;
    fallback_candidates: number;
    total_candidates_before_ranking: number;
    ranked_candidates_returned: number;
    weak_exact_threshold: number | null;
};

export type SearchResult = {
    track: SearchResultTrack;
    queries: SearchQueries;
    counts: SearchCounts;
    format_preference: string;
    search_timeout: number;
    retry_on_timeout: number;
    status: "found" | "not_found" | "error";
    best_candidate: RankedCandidate | null;
    alternative_candidates: RankedCandidate[];
    ranked_candidates: RankedCandidate[];
    error?: string;
};


function App() {
    const [selectedTrackIndex, setSelectedTrackIndex] = useState<number | null>(null)
    const [searchResult, setSearchResult] = useState<any | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [playlistUrl, setPlaylistUrl] = useState("")
    const [tracks, setTracks] = useState<any[]>([])
    const [searchResults, setSearchResults] = useState<Record<number, any>>({})
    const [selectedTracks, setSelectedTracks] = useState<Set<number>>(new Set())
    const [searchProgress, setSearchProgress] = useState<string>("")
    const [concurrency, setConcurrency] = useState<number>(3)
    const searchResultsRef = React.useRef<Record<number, any>>({})
    
    async function handleLoadPlaylist() {
        const response = await fetch("http://localhost:8000/playlist", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                input_type: "spotify_url",
                input_value: playlistUrl
            })
        })
        const data = await response.json()
        setTracks(data.tracks)
    }

    async function handleSearch(tracksToSearch?: number[], autoRetry: boolean = true) {
        console.log("handleSearch called", tracksToSearch, selectedTracks)

        setIsLoading(true)
        const trackArray = tracksToSearch ?? Array.from(selectedTracks)

        for (let i = 0; i < trackArray.length; i += concurrency) {
            const batch = trackArray.slice(i, i + concurrency)
            
            setSearchProgress(`Searching ${i + 1}–${Math.min(i + concurrency, trackArray.length)} of ${trackArray.length}`)

            await Promise.all(
                batch.map(async (index) => {
                    const track = tracks[index]
                    const response = await fetch("http://localhost:8000/search", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(track)
                    })
                    const result = await response.json()
                    setSearchResults(prev => {
                        const next = { ...prev, [index]: result }
                        searchResultsRef.current = next
                        return next
                    })
                })
            )
            await new Promise(r => setTimeout(r, 1000))
        }

        setSearchProgress("Search complete!")
        // Auto-retry not-found tracks once
        if (autoRetry) {
            const notFoundAfterFirstPass = trackArray.filter(
                index => searchResultsRef.current[index]?.status === "not_found" || !searchResultsRef.current[index]
            )

            if (notFoundAfterFirstPass.length > 0) {
                setSearchProgress(`Retrying ${notFoundAfterFirstPass.length} not found tracks...`)
                await new Promise(r => setTimeout(r, 2000))

                for (let i = 0; i < notFoundAfterFirstPass.length; i += concurrency) {
                    const batch = notFoundAfterFirstPass.slice(i, i + concurrency)

                    await Promise.all(
                        batch.map(async (index) => {
                            const track = tracks[index]
                            const response = await fetch("http://localhost:8000/search", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify(track)
                            })
                            const result = await response.json()
                            setSearchResults(prev => {
                                const next = { ...prev, [index]: result }
                                searchResultsRef.current = next
                                return next
                            })
                        })
                    )
                    await new Promise(r => setTimeout(r, 2000))
                }
            }
        }
        setSearchProgress("Search complete!")
        setIsLoading(false)
    }

    async function handleDownload() {
        await Promise.all(
            Object.entries(searchResults).map(async ([_, result]) => {
                if (result.status !== "found" || !result.best_candidate) return
                
                await fetch("http://localhost:8000/download", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(result.best_candidate)
                })
            })
        )
        alert("Downloads queued!")
    }

    const unfoundTracks = Object.entries(searchResults)
            .filter(([_, result]) => result.status === "not_found")
            .map(([index]) => Number(index))

    return (
        <div className="app">
            <header className="header-shell">
                <div className="header-frame outer-frame">
                <div className="header-frame middle-frame">
                    <div className="header-frame inner-frame">
                    <h1 className="title">TRACK HACKER</h1>
                    </div>
                </div>
                </div>
            </header>

            <div className="search-bar">
                <input
                    type="text"
                    placeholder="Paste Spotify URL..."
                    value={playlistUrl}
                    onChange={(e) => setPlaylistUrl(e.target.value)}
                />
                <button onClick={handleLoadPlaylist}>
                    Load Playlist
                </button>
            </div>

            <main className="playlist-panel">
                <div className="controls">
                    {searchProgress && <div className="search-progress">{searchProgress}</div>}
                    <button onClick={() => setSelectedTracks(new Set(tracks.map((_, i) => i)))}>
                        Select All
                    </button>
                    <button onClick={() => setSelectedTracks(new Set())}>
                        Clear All
                    </button>
                    <select
                        value={concurrency}
                        onChange={(e) => setConcurrency(Number(e.target.value))}
                    >
                        {[1, 2, 3, 4, 5].map(n => ( 
                            <option key={n} value={n}>{n} at a time</option>
                        ))}
                    </select>
                    <button onClick={() => handleSearch()}>
                        Search Selected
                    </button>
                    <button onClick={handleDownload}>
                        Download All
                    </button>
                    {unfoundTracks.length > 0 && searchProgress === "Search complete!" && (
                        <button onClick={() => handleSearch(unfoundTracks)}>
                            Retry {unfoundTracks.length} not found
                        </button>
                    )}
                </div>
                <div className="playlist-list">
                {tracks.map((track, index) => (
                    <div
                        key={index}
                        className={`track-row ${selectedTracks.has(index) ? "selected" : ""}`}
                        onClick={() => {
                            setSelectedTracks(prev => {
                                const next = new Set(prev)
                                if (next.has(index)) {
                                    next.delete(index)
                                } else {
                                    next.add(index)
                                }
                                return next
                            })
                        }}
                    >
                        <input
                            type="checkbox"
                            checked={selectedTracks.has(index)}
                            onChange={() => {}}
                        />
                        <span className="track-index">{index + 1}</span>
                        <span className="track-meta">
                            <span>{track.artist}</span>
                            <span className="separator">■</span>
                            <span>{track.title}</span>
                        </span>
                        {searchResults[index] && (
                        <span className="search-status">
                            {searchResults[index].status === "found" 
                                ? `✓ ${searchResults[index].counts.ranked_candidates_returned} candidates`
                                : "✗ not found"
                            }
                        </span>
                    )}
                    </div>
                ))}
                </div>
            </main>
            </div>
    )
}

export default App;


