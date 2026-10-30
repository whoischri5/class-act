// A team's crest, or a circle with its 3-letter code when there's no crest image.
export default function TeamBadge({ team, size = 40 }) {
  if (team.crest_url) {
    return <img src={team.crest_url} alt="" width={size} height={size} className="team-crest" />;
  }
  return (
    <span className="team-tla" style={{ width: size, height: size }}>
      {team.tla || team.name.slice(0, 3).toUpperCase()}
    </span>
  );
}
