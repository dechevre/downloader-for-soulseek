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
    const [searchResults, setSearchResults] = useState<Record<number, SearchResult>>({})
    const [selectedTracks, setSelectedTracks] = useState<Set<number>>(new Set())
    const [searchProgress, setSearchProgress] = useState<string>("")
    const [concurrency, setConcurrency] = useState<number>(1)
    const searchResultsRef = React.useRef<Record<number, any>>({})
    const [selectedCandidates, setSelectedCandidates] = useState<Record<number, RankedCandidate | null>>({});
    const [formatPreference, setFormatPreference] = useState<string>("best_available")
    const [retryingTracks, setRetryingTracks] = useState<Set<number>>(new Set())
    const [downloadSubfolder, setDownloadSubfolder] = useState<string>("Track Hacker Music")
    const [downloadDir, setDownloadDir] = useState<string>("")
    const [slskdReady, setSlskdReady] = useState<boolean>(false)
    const [setupSlskdPath, setSetupSlskdPath] = useState<string>("~/slskd/slskd")
    const [setupUsername, setSetupUsername] = useState<string>("")
    const [setupPassword, setSetupPassword] = useState<string>("")
    const [setupSubfolder, setSetupSubfolder] = useState<string>("Track Hacker Music")
    const [setupError, setSetupError] = useState<string | null>(null)
    const [autoDownload, setAutoDownload] = useState<boolean>(false)
    const [downloadStatuses, setDownloadStatuses] = useState<Record<string, string>>({})


    React.useEffect(() => {
        fetch("http://localhost:8000/health")
            .then(r => r.json())
            .then(data => setSlskdReady(data.slskd === "ok"))
        
        fetch("http://localhost:8000/config")
            .then(r => r.json())
            .then(data => setDownloadDir(data.download_dir))
    }, [])

    React.useEffect(() => {
        const interval = setInterval(() => {
            fetch("http://localhost:8000/downloads/status")
                .then(r => r.json())
                .then(data => {
                    const statuses: Record<string, string> = {}
                    for (const user of data.downloads) {
                        for (const dir of user.directories) {
                            for (const file of dir.files) {
                                statuses[file.filename] = file.state
                            }
                        }
                    }
                    setDownloadStatuses(statuses)
                })
        }, 5000)
        return () => clearInterval(interval)
    }, [])

    async function handleSetup() {
        setSetupError(null)
        const response = await fetch("http://localhost:8000/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                slskd_path: setupSlskdPath,
                username: setupUsername,
                password: setupPassword,
                download_subfolder: setupSubfolder
            })
        })
        const data = await response.json()
        if (data.status === "ok") {
            setSlskdReady(true)
            setDownloadDir(data.download_dir)
        } else {
            setSetupError(data.error)
        }
    }

    async function handleSaveConfig() {
        const response = await fetch("http://localhost:8000/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
                subfolder: downloadSubfolder 
            })
        })
        const data = await response.json()
        if (data.status === "ok") {
            setDownloadDir(data.download_dir)
        }
    }
    

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
        setSelectedTracks(new Set(data.tracks.map((_: any, i: number) => i)))
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
                        body: JSON.stringify({ ...track, format_preference: formatPreference })
                    })
                    const result = await response.json()
                    setSearchResults(prev => {
                        const next = { ...prev, [index]: result }
                        searchResultsRef.current = next
                        return next
                    })
                    setSelectedCandidates(prev => ({
                        ...prev,
                        [index]: result.best_candidate ?? null
                    }))
                    if (autoDownload && result.best_candidate) {
                        await fetch("http://localhost:8000/download", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(result.best_candidate)
                        })
                        await new Promise(r => setTimeout(r, 500))
                    }
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
            setRetryingTracks(new Set(notFoundAfterFirstPass))


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
                                body: JSON.stringify({ ...track, format_preference: formatPreference })
                            })
                            const result = await response.json()
                            setSearchResults(prev => {
                                const next = { ...prev, [index]: result }
                                searchResultsRef.current = next
                                return next
                            })
                            setSelectedCandidates(prev => ({
                                ...prev,
                                [index]: result.best_candidate ?? null
                            }))
                            if (autoDownload && result.best_candidate) {
                                await fetch("http://localhost:8000/download", {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify(result.best_candidate)
                                })
                                await new Promise(r => setTimeout(r, 500))
                            }
                        })
                    )
                    await new Promise(r => setTimeout(r, 2000))
                }
            }
        }
        setRetryingTracks(new Set())
        setSearchProgress("Search complete!")
        setIsLoading(false)
    }

    async function handleDownload() {
        for (const [idx, candidate] of Object.entries(selectedCandidates)) {
            if (!candidate) continue
            if(!selectedTracks.has(Number(idx))) continue
            await fetch("http://localhost:8000/download", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(candidate)
            })
            await new Promise(r => setTimeout(r, 500))
        }
        alert("Downloads queued!")
    }

    const unfoundTracks = Object.entries(searchResults)
            .filter(([_, result]) => result.status === "not_found")
            .map(([index]) => Number(index))

    if (!slskdReady) {
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
                <div className="setup-panel">
                    <h2>Setup</h2>
                    <p>Configure Track Hacker to get started.</p>
                    <label>Soulseek Username</label>
                    <input
                        type="text"
                        value={setupUsername}
                        onChange={e => setSetupUsername(e.target.value)}
                        placeholder="your soulseek username"
                    />
                    <label>Soulseek Password</label>
                    <input
                        type="password"
                        value={setupPassword}
                        onChange={e => setSetupPassword(e.target.value)}
                        placeholder="your soulseek password"
                    />
                    <label>slskd path</label>
                    <input
                        type="text"
                        value={setupSlskdPath}
                        onChange={e => setSetupSlskdPath(e.target.value)}
                        placeholder="~/slskd/slskd"
                    />
                    <label>Download folder name</label>
                    <input
                        type="text"
                        value={setupSubfolder}
                        onChange={e => setSetupSubfolder(e.target.value)}
                        placeholder="Track Hacker Music"
                    />
                    {setupError && <p className="error">{setupError}</p>}
                    <button onClick={handleSetup}>Start Track Hacker</button>
                </div>
            </div>
        )
    }

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
                    <label>
                        <input
                            type="checkbox"
                            checked={autoDownload}
                            onChange={e => setAutoDownload(e.target.checked)}
                        />
                        Auto-download best candidate
                    </label>
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
                        {[1, 2, 3].map(n => ( 
                            <option key={n} value={n}>{n} at a time</option>
                        ))}
                    </select>
                    <select
                        value={formatPreference}
                        onChange={(e) => setFormatPreference(e.target.value)}
                    >
                        <option value="best_available">Best Available</option>
                        <option value="cdj_safe">CDJ Safe</option>
                        <option value="mp3_preferred">MP3 Preferred</option>
                        <option value="lossless_preferred">Lossless Preferred</option>
                        <option value="wav_aiff_only">WAV/AIFF Only</option>
                    </select>
                    <input
                        type="text"
                        value={downloadSubfolder}
                        onChange={e => setDownloadSubfolder(e.target.value)}
                        placeholder="Track Hacker Music"
                    />
                    <button onClick={handleSaveConfig}>Save Path</button>
                    {downloadDir && <span className="download-path">{downloadDir}</span>}
                    <button onClick={() => handleSearch()}>
                        Search Selected
                    </button>
                    <button onClick={handleDownload}>
                        Download Selected
                    </button>
                    {unfoundTracks.length > 0 && searchProgress === "Search complete!" && (
                        <button onClick={() => handleSearch(unfoundTracks)}>
                            Retry {unfoundTracks.length} not found
                        </button>
                    )}
                </div>
                <div className="playlist-list">
                    {tracks.map((track, index) => (
                        <React.Fragment key={index}>
                            <div
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
                                            : retryingTracks.has(index)
                                                ? "⟳ retrying..."
                                                : "✗ not found"
                                        }
                                    </span>
                                )}
                                {selectedCandidates[index] && downloadStatuses[selectedCandidates[index]!.filename] && (
                                    <span className="download-status">
                                        {downloadStatuses[selectedCandidates[index]!.filename] === "Completed, Succeeded"
                                            ? "✓ downloaded"
                                            : downloadStatuses[selectedCandidates[index]!.filename] === "Completed, TimedOut"
                                                ? "⟳ retrying..."
                                                : downloadStatuses[selectedCandidates[index]!.filename] === "Completed, Errored"
                                                    ? "✗ failed"
                                                    : "⬇ downloading..."
                                        }
                                    </span>
                                )}
                            </div>
                            {searchResults[index]?.status === "found" && (
                                <TrackCard
                                    result={searchResults[index]}
                                    selectedCandidate={selectedCandidates[index] ?? null}
                                    onSelectCandidate={(c) => setSelectedCandidates(prev => ({ ...prev, [index]: c }))}
                                />
                            )}
                        </React.Fragment>
                    ))}
                </div>
            </main>
        </div>
    )
}

export default App;