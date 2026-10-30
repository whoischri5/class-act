import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Form, Row } from "react-bootstrap";
import { errorMessage, getTeams, predictMatch } from "../api";
import Loading from "./Loading";
import ProbabilityBar from "./ProbabilityBar";

// Pick any two teams and get a prediction — handy for "what if they met in the final?"
export default function MatchupPredictor() {
  const [teams, setTeams] = useState([]);
  const [homeId, setHomeId] = useState("");
  const [awayId, setAwayId] = useState("");
  const [neutral, setNeutral] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getTeams()
      .then((data) => {
        setTeams(data);
        if (data.length >= 2) {
          setHomeId(String(data[0].id));
          setAwayId(String(data[1].id));
        }
      })
      .catch((err) => setError(errorMessage(err)));
  }, []);

  function handleSubmit(event) {
    event.preventDefault(); // stop the browser from reloading the page
    setError(null);
    predictMatch(homeId, awayId, neutral)
      .then(setResult)
      .catch((err) => setError(errorMessage(err)));
  }

  if (teams.length === 0 && !error) return <Loading label="Loading teams…" />;

  const teamOptions = teams.map((t) => (
    <option key={t.id} value={t.id}>
      {t.name} (Elo {Math.round(t.elo)})
    </option>
  ));

  return (
    <Card className="shadow-sm">
      <Card.Body>
        <Form onSubmit={handleSubmit}>
          <Row className="g-2 align-items-end">
            <Col md>
              <Form.Label>Home team</Form.Label>
              <Form.Select value={homeId} onChange={(e) => setHomeId(e.target.value)}>{teamOptions}</Form.Select>
            </Col>
            <Col md>
              <Form.Label>Away team</Form.Label>
              <Form.Select value={awayId} onChange={(e) => setAwayId(e.target.value)}>{teamOptions}</Form.Select>
            </Col>
          </Row>
          <div className="d-flex justify-content-between align-items-center mt-3">
            <Form.Check
              type="switch"
              id="neutral"
              label="Neutral venue (like the final)"
              checked={neutral}
              onChange={(e) => setNeutral(e.target.checked)}
            />
            <Button type="submit" disabled={homeId === awayId}>Predict</Button>
          </div>
        </Form>

        {error && <Alert variant="danger" className="mt-3 mb-0">{error}</Alert>}

        {result && (
          <div className="mt-4">
            <h5 className="text-center mb-3">
              {result.home_team.name} vs {result.away_team.name}
            </h5>
            <ProbabilityBar
              prediction={result}
              homeLabel={result.home_team.tla || "Home"}
              awayLabel={result.away_team.tla || "Away"}
            />
            <p className="small text-muted mt-3 mb-0">
              Current Elo {Math.round(result.home_team.elo)} vs {Math.round(result.away_team.elo)} ·
              recent form {result.home_team.form} vs {result.away_team.form} points per game
            </p>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
