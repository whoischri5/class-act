import { useEffect, useState } from "react";
import { Alert, Card, Table } from "react-bootstrap";
import { errorMessage, getModelInfo } from "../api";
import Loading from "./Loading";

// Shows how the model scored on a season it never saw during training.
export default function ModelInfo() {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getModelInfo().then(setInfo).catch((err) => setError(errorMessage(err)));
  }, []);

  if (error) return <Alert variant="danger">{error}</Alert>;
  if (!info) return <Loading />;

  const m = info.metrics;
  const season = (s) => `${s}/${String(s + 1).slice(2)}`;

  return (
    <Card className="shadow-sm">
      <Card.Body>
        <p>
          A logistic regression on the difference in <strong>Elo rating</strong>,{" "}
          <strong>recent form</strong> and <strong>goal difference</strong> between the two teams.
          Trained on {info.train_seasons.map(season).join(", ")} and tested on{" "}
          <strong>{season(info.test_season)}</strong> ({m.test_matches} matches it never saw).
        </p>

        <Table size="sm" bordered>
          <thead>
            <tr><th></th><th>Model</th><th>Baseline</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>Log loss <span className="text-muted small">(lower is better)</span></td>
              <td><strong>{m.log_loss_model}</strong></td>
              <td>{m.log_loss_baseline} <span className="text-muted small">(historical base rates)</span></td>
            </tr>
            <tr>
              <td>Accuracy</td>
              <td><strong>{Math.round(m.accuracy_model * 100)}%</strong></td>
              <td>{Math.round(m.accuracy_always_home * 100)}% <span className="text-muted small">(always pick home)</span></td>
            </tr>
          </tbody>
        </Table>

        <h6 className="mt-4">Calibration: when the model says X%, does it happen X% of the time?</h6>
        <Table size="sm" bordered>
          <thead>
            <tr><th>Predicted home win</th><th>Avg predicted</th><th>Actually happened</th><th>Matches</th></tr>
          </thead>
          <tbody>
            {m.calibration_home_win.map((row) => (
              <tr key={row.bucket}>
                <td>{row.bucket}</td>
                <td>{Math.round(row.avg_predicted * 100)}%</td>
                <td>{Math.round(row.actual_rate * 100)}%</td>
                <td>{row.matches}</td>
              </tr>
            ))}
          </tbody>
        </Table>
        <p className="small text-muted mb-0">Trained {new Date(info.trained_at).toLocaleString()}.</p>
      </Card.Body>
    </Card>
  );
}
