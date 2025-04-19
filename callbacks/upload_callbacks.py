from dash import Input, Output, State, callback

from utils.file_utils import parse_content


@callback(
    Output("iat-upload-status", "children"),
    [Input("upload-iat", "contents")],
    [State("upload-iat", "filename")],
)
def update_iat_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@callback(
    Output("hsp-upload-status", "children"),
    [Input("upload-hsp", "contents")],
    [State("upload-hsp", "filename")],
)
def update_hsp_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@callback(
    Output("csp-upload-status", "children"),
    [Input("upload-csp", "contents")],
    [State("upload-csp", "filename")],
)
def update_csp_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@callback(
    Output("airflow-upload-status", "children"),
    [Input("upload-airflow", "contents")],
    [State("upload-airflow", "filename")],
)
def update_airflow_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@callback(
    Output("ahu-dat-upload-status", "children"),
    [Input("upload-ahu-dat", "contents")],
    [State("upload-ahu-dat", "filename")],
)
def update_ahu_dat_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@callback(
    Output("map-upload-status", "children"),
    [Input("upload-map", "contents")],
    [State("upload-map", "filename")],
)
def update_map_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status


@callback(
    Output("cooling-upload-status", "children"),
    [Input("upload-cooling", "contents")],
    [State("upload-cooling", "filename")],
)
def update_cooling_status(contents, filename):
    if contents is None:
        return ""
    df, status = parse_content(contents, filename)
    return status
