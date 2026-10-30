import { ProgressBar } from "react-bootstrap";

const pct = (p) => Math.round(p * 100);

// One horizontal bar split into Home / Draw / Away.
export default function ProbabilityBar({ prediction, homeLabel = "Home", awayLabel = "Away" }) {
  const { prob_home_win: home, prob_draw: draw, prob_away_win: away } = prediction;
  return (
    <div>
      <ProgressBar className="prob-bar">
        <ProgressBar now={pct(home)} className="prob-home" label={`${pct(home)}%`} />
        <ProgressBar now={pct(draw)} className="prob-draw" label={`${pct(draw)}%`} />
        <ProgressBar now={pct(away)} className="prob-away" label={`${pct(away)}%`} />
      </ProgressBar>
      <div className="d-flex justify-content-between small text-muted mt-1">
        <span>{homeLabel} win</span>
        <span>Draw</span>
        <span>{awayLabel} win</span>
      </div>
    </div>
  );
}
