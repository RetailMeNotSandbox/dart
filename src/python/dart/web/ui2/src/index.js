import 'babel-polyfill';
import React, { PropTypes } from 'react';
import { Provider } from 'react-redux';
import { render } from 'react-dom';
import { BrowserRouter as Router, Route } from 'react-router-dom';

import createHistory from 'history/createBrowserHistory'
import configureStore from 'configureStore';
import Header from 'components/Header'
import Graph from 'scenes/Graph'
import './index.css';

const Root = ({ store, history }) => (
  <Provider store={store}>
      <div>
          <Header/>
          <Router history={history} >
              <Route path="/graph/:type/:id" component={Graph} />
          </Router>
      </div>
  </Provider>
);

Root.propTypes = {
    store: PropTypes.object.isRequired,
    history: PropTypes.object.isRequired
};

const history = createHistory();
const store = configureStore(history);

render(
  <Root store={store} history={history} />,
  document.getElementById('root')
);
