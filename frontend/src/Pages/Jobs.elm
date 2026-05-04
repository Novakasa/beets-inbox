module Pages.Jobs exposing (Model, Msg, init, update, view)

import Api
import Html exposing (..)
import Html.Attributes exposing (..)
import Html.Events exposing (..)
import Http
import Types exposing (..)


-- ── Model ─────────────────────────────────────────────────────────────────────


type alias Model =
    { jobs : List Job
    , loading : Bool
    , error : Maybe String
    , detail : Maybe Job
    }


-- ── Msg ───────────────────────────────────────────────────────────────────────


type Msg
    = GotJobs (Result Http.Error (List Job))
    | Refresh
    | OpenDetail Job
    | CloseDetail


-- ── Init ──────────────────────────────────────────────────────────────────────


init : ( Model, Cmd Msg )
init =
    ( { jobs = [], loading = True, error = Nothing, detail = Nothing }
    , Api.getJobs GotJobs
    )


-- ── Update ────────────────────────────────────────────────────────────────────


update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        Refresh ->
            ( { model | loading = True, error = Nothing }
            , Api.getJobs GotJobs
            )

        GotJobs (Ok jobs) ->
            ( { model | jobs = jobs, loading = False }, Cmd.none )

        GotJobs (Err err) ->
            ( { model | error = Just (httpErrorToString err), loading = False }, Cmd.none )

        OpenDetail job ->
            ( { model | detail = Just job }, Cmd.none )

        CloseDetail ->
            ( { model | detail = Nothing }, Cmd.none )


-- ── View ──────────────────────────────────────────────────────────────────────


view : Model -> Html Msg
view model =
    div [ class "jobs-page" ]
        [ div [ class "page-header" ]
            [ h1 [] [ text "Import history" ]
            , button [ onClick Refresh, class "btn" ] [ text "↻ Refresh" ]
            ]
        , case model.detail of
            Just job ->
                viewDetail job

            Nothing ->
                viewList model
        ]


viewList : Model -> Html Msg
viewList model =
    if model.loading then
        p [ class "loading" ] [ text "Loading…" ]

    else
        case model.error of
            Just err ->
                p [ class "error-msg" ] [ text err ]

            Nothing ->
                if List.isEmpty model.jobs then
                    p [ class "empty-msg" ] [ text "No import jobs yet." ]

                else
                    table [ class "jobs-table" ]
                        [ thead []
                            [ tr []
                                [ th [] [ text "Status" ]
                                , th [] [ text "File" ]
                                , th [] [ text "Artist" ]
                                , th [] [ text "Album" ]
                                , th [] [ text "Created" ]
                                ]
                            ]
                        , tbody [] (List.map viewRow model.jobs)
                        ]


viewRow : Job -> Html Msg
viewRow job =
    tr
        [ onClick (OpenDetail job)
        , class ("job-row status-" ++ jobStatusLabel job.status)
        ]
        [ td [] [ viewBadge job.status ]
        , td [] [ text (basename job.sourcePath) ]
        , td [] [ text (Maybe.withDefault "—" job.artist) ]
        , td [] [ text (Maybe.withDefault "—" job.album) ]
        , td [] [ text job.createdAt ]
        ]


viewDetail : Job -> Html Msg
viewDetail job =
    div [ class "job-detail" ]
        [ button [ onClick CloseDetail, class "btn" ] [ text "← Back" ]
        , h2 [] [ text (basename job.sourcePath) ]
        , dl [ class "detail-list" ]
            [ dt [] [ text "Status" ]
            , dd [] [ viewBadge job.status ]
            , dt [] [ text "Artist" ]
            , dd [] [ text (Maybe.withDefault "—" job.artist) ]
            , dt [] [ text "Album" ]
            , dd [] [ text (Maybe.withDefault "—" job.album) ]
            , dt [] [ text "Category" ]
            , dd [] [ text (Maybe.withDefault "—" job.category) ]
            , dt [] [ text "Created" ]
            , dd [] [ text job.createdAt ]
            , dt [] [ text "Completed" ]
            , dd [] [ text (Maybe.withDefault "—" job.completedAt) ]
            ]
        , if String.isEmpty job.log then
            text ""

          else
            div [ class "job-log" ]
                [ h3 [] [ text "Log" ]
                , pre [] [ text job.log ]
                ]
        ]


viewBadge : JobStatus -> Html Msg
viewBadge status =
    span [ class ("badge badge-" ++ jobStatusLabel status) ]
        [ text (jobStatusLabel status) ]


-- ── Helpers ───────────────────────────────────────────────────────────────────


basename : String -> String
basename path =
    path
        |> String.split "/"
        |> List.reverse
        |> List.head
        |> Maybe.withDefault path
