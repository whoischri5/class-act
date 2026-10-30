import { useEffect, useState } from "react";
import { Alert, Container, Nav, Navbar, Tab } from "react-bootstrap";
import { getHealth } from "./api";
import FixtureList from "./components/FixtureList";
import MatchupPredictor from "./components/MatchupPredictor";
import ModelInfo from "./components/ModelInfo";

export default function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []); // [] = run once, when the page first loads

  return (
    <>
      <Navbar bg="dark" variant="dark" className="mb-4">
        <Container>
          <Navbar.Brand>⚽ UCL Match Predictor</Navbar.Brand>
          {health?.model_version && (
            <Navbar.Text className="small">model: {health.model_version}</Navbar.Text>
          )}
        </Container>
      </Navbar>

      <Container className="pb-5" style={{ maxWidth: 860 }}>
        {health?.data_source === "sample" && (
          <Alert variant="warning" className="small">
            <strong>Sample data.</strong> These results are simulated so the app can run
            without an API key. Load real data with <code>scripts.fetch_history</code>.
          </Alert>
        )}

        <Tab.Container defaultActiveKey="fixtures">
          <Nav variant="pills" className="mb-3">
            <Nav.Item>
              <Nav.Link eventKey="fixtures">Upcoming fixtures</Nav.Link>
            </Nav.Item>
            <Nav.Item>
              <Nav.Link eventKey="matchup">Any matchup</Nav.Link>
            </Nav.Item>
            <Nav.Item>
              <Nav.Link eventKey="model">How good is the model?</Nav.Link>
            </Nav.Item>
          </Nav>
          <Tab.Content>
            <Tab.Pane eventKey="fixtures">
              <FixtureList />
            </Tab.Pane>
            <Tab.Pane eventKey="matchup">
              <MatchupPredictor />
            </Tab.Pane>
            <Tab.Pane eventKey="model" mountOnEnter>
              <ModelInfo />
            </Tab.Pane>
          </Tab.Content>
        </Tab.Container>
      </Container>
    </>
  );
}
