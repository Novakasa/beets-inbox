module Main exposing (main)

import Browser
import Html exposing (..)
import Html.Attributes exposing (..)
import Pages.Inbox as Inbox


-- ── Types ─────────────────────────────────────────────────────────────────────


type alias Model =
    { inbox : Inbox.Model }


type Msg
    = InboxMsg Inbox.Msg


-- ── Init ──────────────────────────────────────────────────────────────────────


init : () -> ( Model, Cmd Msg )
init _ =
    let
        ( m, cmd ) =
            Inbox.init
    in
    ( { inbox = m }, Cmd.map InboxMsg cmd )


-- ── Update ────────────────────────────────────────────────────────────────────


update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        InboxMsg sub ->
            let
                ( newM, cmd ) =
                    Inbox.update sub model.inbox
            in
            ( { model | inbox = newM }, Cmd.map InboxMsg cmd )


-- ── View ──────────────────────────────────────────────────────────────────────


view : Model -> Html Msg
view model =
    div [ class "app" ]
        [ nav [ class "app-nav" ]
            [ h1 [ class "app-title" ] [ text "beets-inbox" ] ]
        , div [ class "page-content" ]
            [ Html.map InboxMsg (Inbox.view model.inbox) ]
        ]


-- ── Main ──────────────────────────────────────────────────────────────────────


main : Program () Model Msg
main =
    Browser.element
        { init = init
        , update = update
        , view = view
        , subscriptions = \_ -> Sub.none
        }
