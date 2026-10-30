import { useEffect, useState } from "react";
import { Alert, Button } from "react-bootstrap";
import { errorMessage, getFixturePredictions } from "../api";
import FixtureCard from "./FixtureCard";
import Loading from "./Loading";

export default function FixtureList() {
  const [fixtures, setFixtures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  function load() {
    setLoading(true);
    setError(null);
    getFixturePredictions()
      .then(setFixtures)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  }

  useEffect(load, []); // fetch once when the component first appears

  if (loading) return <Loading label="Loading fixtures and predictions…" />;
  if (error)
    return (
      <Alert variant="danger">
        {error}{" "}
        <Button size="sm" variant="outline-danger" onClick={load}>Try again</Button>
      </Alert>
    );
  if (fixtures.length === 0)
    return <Alert variant="info">No upcoming Champions League fixtures right now.</Alert>;

  return (
    <div>
      {fixtures.map((f) => (
        <FixtureCard key={f.id} fixture={f} />
      ))}
    </div>
  );
}
