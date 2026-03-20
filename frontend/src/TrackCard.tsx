type Track = {
    artist: string;
    title: string;
    duration: number;
}

type TrackCardProps = {
    track: Track;
};

export default function TrackCard({ track }: TrackCardProps) { // destructing, pull out track from incoming TCP
    return (
        <div>
            <h2>
                <span>{track.artist.toUpperCase()}</span>
                <span className="separator"> ▣ </span> 
                <span>{track.title.toUpperCase()}</span>
            </h2>
            <p className="duration">
                DURATION: {track.duration}s
            </p>
        </div>
    )
}