import React, { useState } from "react";
import TrackCard from "./TrackCard"
import "./App.css"

type Track = {
    artist: string;
    title: string;
    duration: number; // Duration in seconds
}

const tracks: Track[] = [
    {
        artist: "Boney M.",
        title: "Daddy Cool",
        duration: 0,
    },
    {
        artist: "Drexciya",
        title: "Andreaen Sand Dunes",
        duration: 0,
    },
    {
        artist: "Aphex Twin",
        title: "Xtal",
        duration: 0,
    },
]

function App() {
    const [selectedTrackIndex, setSelectedTrackIndex] = useState<number | null>(null)
    const [searchResult, setSearchResult] = useState<any | null>(null)
    const [isLoading, setIsLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

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

            <main className="playlist-panel">
                <div className="playlist-list">
                {tracks.map((track, index) => (
                    <button
                    key={index}
                    className={`track-row ${selectedTrackIndex === index ? "selected" : ""}`}
                    onClick={() => setSelectedTrackIndex(index)}
                    >
                    <span className="track-index">{index + 1}</span>
                    <span className="track-meta">
                        <span>{track.artist}</span>
                        <span className="separator">■</span>
                        <span>{track.title}</span>
                    </span>
                    </button>
                ))}
                </div>
            </main>
            </div>
    )
}

export default App;

async function handleTrackClick(index: number) {

}