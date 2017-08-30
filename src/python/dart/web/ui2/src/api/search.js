import axios from 'axios';

export const getResults = state => state.results;
export const getQuery = state => state.query;
export const getIsFetching = state => state.isFetching;

const SEARCH_REQUEST = 'SEARCH_REQUEST';
const searchRequest = query => ({
    type: SEARCH_REQUEST,
    query
});

const SEARCH_SUCCESS = 'SEARCH_SUCCESS';
const searchSuccess = (query, response) => ({
    type: SEARCH_SUCCESS,
    query,
    response
});

const SEARCH_FAILURE = 'SEARCH_FAILURE';
const searchFailure = (query, error) => ({
    type: SEARCH_FAILURE,
    query,
    message: error.message || 'Something went wrong.'
});

export const search = query => (dispatch, getState) => {
    const state = getState();
    if (getQuery(state) === query && getIsFetching(state))
        return Promise.resolve();

    dispatch(searchRequest(query));

    const source = axios.CancelToken.source();
    return {
        promise: axios.get('/api/1/workflow', {
            cancelToken: source.token,
            params: {
                limit: 10,
                filters: [`name ~ ${query}`]
            }
        }).then(
            response => {
                dispatch(searchSuccess(query, response));
                return response;
            }, error => {
                dispatch(searchFailure(query, error));
                return error;
            }
        ),
        cancel: source.cancel
    };
};

export default (
    state = {
        results: [],
        isFetching: false,
        query: null
    },
    action
) => {
    switch (action.type) {
        case SEARCH_REQUEST:
            return {
                ...state,
                results: [],
                isFetching: true,
                query: action.query
            };
        case SEARCH_SUCCESS:
            if (action.query !== state.query)
                return state;

            return {
                ...state,
                results: action.response.data.results,
                isFetching: false
            };
        case SEARCH_FAILURE:
            if (action.query !== state.query)
                return state;

            return {
                ...state,
                results: [],
                isFetching: false
            };
        default:
            return state;
    }
};