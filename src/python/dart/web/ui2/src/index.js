import 'babel-polyfill';
import React, { PropTypes } from 'react';
import { Provider } from 'react-redux';
import { render } from 'react-dom';
import { Route } from 'react-router-dom';
import { ConnectedRouter } from 'react-router-redux';
import 'assets/react-toolbox/theme.css';
import theme from 'assets/react-toolbox/theme.js';
import ThemeProvider from 'react-toolbox/lib/ThemeProvider';
import MuiThemeProvider from 'material-ui/styles/MuiThemeProvider';

import createHistory from 'history/createBrowserHistory'
import configureStore from 'configureStore';
import Header from 'components/Header';
import Graph from 'scenes/Graph';
import Search from 'scenes/Search'
import './index.css';

const Root = ({ store, history }) => (
    <MuiThemeProvider>
        <ThemeProvider theme={theme}>
            <Provider store={store}>
                <div style={{height: '100%'}} >
                    <Header/>
                    <ConnectedRouter history={history} >
                        <div style={{height: '100%'}} >
                            <Route
                                exact
                                path="/"
                                component={Search}
                            />
                            <Route
                                path="/graph/:type/:id"
                                component={Graph}
                            />
                        </div>
                    </ConnectedRouter>
                </div>
            </Provider>
        </ThemeProvider>
    </MuiThemeProvider>
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
