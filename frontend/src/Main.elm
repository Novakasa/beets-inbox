module Main exposing (main)

import Browser
import Html exposing (..)
import Html.Attributes exposing (..)
import Html.Events exposing (..)
import Pages.Inbox as Inbox
import Pages.Jobs as Jobs


-- ── Types ─────────────────────────────────────────────────────────────────────


type Page
    = InboxPage Inbox.Model
    | JobsPage Jobs.Model


type Nav
    = NavInbox
    | NavJobs


type alias Model =
    { page : Page }


type Msg
    = GoTo Nav
    | InboxMsg Inbox.Msg
    | JobsMsg Jobs.Msg


-- ── Init ──────────────────────────────────────────────────────────────────────


init : () -> ( Model, Cmd Msg )
init _ =
    let
        ( m, cmd ) =
            Inbox.init
    in
    ( { page = InboxPage m }, Cmd.map InboxMsg cmd )


-- ── Update ────────────────────────────────────────────────────────────────────


update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        GoTo NavInbox ->
            let
                ( m, cmd ) =
                    Inbox.init
            in
            ( { model | page = InboxPage m }, Cmd.map InboxMsg cmd )

        GoTo NavJobs ->
            let
                ( m, cmd ) =
                    Jobs.init
            in
            ( { model | page = JobsPage m }, Cmd.map JobsMsg cmd )

        InboxMsg sub ->
            case model.page of
                InboxPage m ->
                    let
                        ( newM, cmd ) =
                            Inbox.update sub m
                    in
                    ( { model | page = InboxPage newM }, Cmd.map InboxMsg cmd )

                _ ->
                    ( model, Cmd.none )

        JobsMsg sub ->
            case model.page of
                JobsPage m ->
                    let
                        ( newM, cmd ) =
                            Jobs.update sub m
                    in
                    ( { model | page = JobsPage newM }, Cmd.map JobsMsg cmd )

                _ ->
                    ( model, Cmd.none )


-- ── View ──────────────────────────────────────────────────────────────────────


view : Model -> Html Msg
view model =
    div [ class "app" ]
        [ viewNav model.page
        , div [ class "page-content" ]
            [ case model.page of
                InboxPage m ->
                    Html.map InboxMsg (Inbox.view m)

                JobsPage m ->
                    Html.map JobsMsg (Jobs.view m)
            ]
        ]


viewNav : Page -> Html Msg
viewNav page =
    nav [ class "app-nav" ]
        [ h1 [ class "app-title" ] [ text "beets-inbox" ]
        , div [ class "nav-links" ]
            [ navButton (GoTo NavInbox) "📥 Inbox" (isInboxPage page)
            , navButton (GoTo NavJobs) "📋 Jobs" (isJobsPage page)
            ]
        ]


navButton : Msg -> String -> Bool -> Html Msg
navButton msg label_ isActive =
    button
        [ onClick msg
        , classList [ ( "nav-btn", True ), ( "active", isActive ) ]
        ]
        [ text label_ ]


isInboxPage : Page -> Bool
isInboxPage page =
    case page of
        InboxPage _ ->
            True

        _ ->
            False


isJobsPage : Page -> Bool
isJobsPage page =
    case page of
        JobsPage _ ->
            True

        _ ->
            False


-- ── Main ──────────────────────────────────────────────────────────────────────


main : Program () Model Msg
main =
    Browser.element
        { init = init
        , update = update
        , view = view
        , subscriptions = \_ -> Sub.none
        }
