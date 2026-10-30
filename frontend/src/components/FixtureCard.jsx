import { Card } from "react-bootstrap";
import ProbabilityBar from "./ProbabilityBar";
import TeamBadge from "./TeamBadge";

const formatStage = (stage) =>
  (stage || "").toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

function TeamSide({ team, align }) {
  return (
    <div className={`d-flex align-items-center gap-2 flex-1 justify-content-${align}`}>
      {align === "end" && <strong className="text-end">{team.short_name || team.name}</strong>}
      <TeamBadge team={team} />
      {align === "start" && <strong>{team.short_name || team.name}</strong>}
    </div>
  );
}

export default function FixtureCard({ fixture }) {
  const { home_team: home, away_team: away, prediction } = fixture;
  // The API sends UTC times without a "Z"; add it so the browser converts to local time.
  const kickoff = new Date(fixture.match_date + "Z");

  return (
    <Card className="mb-3 shadow-sm">
      <Card.Body>
        <div className="d-flex justify-content-between small text-muted mb-2">
          <span>{formatStage(fixture.stage)}{fixture.neutral && " · neutral venue"}</span>
          <span>{kickoff.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
        </div>
        <div className="d-flex align-items-center mb-3">
          <TeamSide team={home} align="end" />
          <span className="mx-3 text-muted">vs</span>
          <TeamSide team={away} align="start" />
        </div>
        {prediction && (
          <ProbabilityBar
            prediction={prediction}
            homeLabel={home.tla || "Home"}
            awayLabel={away.tla || "Away"}
          />
        )}
      </Card.Body>
    </Card>
  );
}
