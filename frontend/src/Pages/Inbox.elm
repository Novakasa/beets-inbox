module Pages.Inbox exposing (Model, Msg, init, update, view)

import Api
import File exposing (File)
import File.Select as Select
import Html exposing (..)
import Html.Attributes exposing (..)
import Html.Events exposing (..)
import Http
import Types exposing (..)


-- ── Model ─────────────────────────────────────────────────────────────────────


type alias Model =
    { items : List InboxItem
    , categories : List String
    , loading : Bool
    , error : Maybe String
    , editing : Maybe ( String, EditForm ) -- (item id, draft)
    , filterCategory : Maybe String
    , pendingFiles : List File
    , uploadCategory : String
    , uploading : Bool
    , uploadError : Maybe String
    }


-- ── Msg ───────────────────────────────────────────────────────────────────────


type Msg
    = GotItems (Result Http.Error (List InboxItem))
    | GotCategories (Result Http.Error (List String))
    | Refresh
    | StartEdit InboxItem
    | CancelEdit
    | UpdateForm (EditForm -> EditForm)
    | SubmitImport String
    | GotImportResult String (Result Http.Error Job)
    | Discard String
    | GotDiscardResult String (Result Http.Error ())
    | PickFiles
    | GotFiles File (List File)
    | SetUploadCategory String
    | Upload
    | GotUploadResult (Result Http.Error ())
    | SetFilter (Maybe String)


-- ── Init ──────────────────────────────────────────────────────────────────────


init : ( Model, Cmd Msg )
init =
    ( { items = []
      , categories = []
      , loading = True
      , error = Nothing
      , editing = Nothing
      , filterCategory = Nothing
      , pendingFiles = []
      , uploadCategory = ""
      , uploading = False
      , uploadError = Nothing
      }
    , Cmd.batch
        [ Api.getInbox GotItems
        , Api.getCategories GotCategories
        ]
    )


-- ── Update ────────────────────────────────────────────────────────────────────


update : Msg -> Model -> ( Model, Cmd Msg )
update msg model =
    case msg of
        Refresh ->
            ( { model | loading = True, error = Nothing }
            , Cmd.batch [ Api.getInbox GotItems, Api.getCategories GotCategories ]
            )

        GotItems (Ok items) ->
            ( { model | items = items, loading = False }, Cmd.none )

        GotItems (Err err) ->
            ( { model | error = Just (httpErrorToString err), loading = False }, Cmd.none )

        GotCategories (Ok cats) ->
            ( { model
                | categories = cats
                , uploadCategory =
                    if String.isEmpty model.uploadCategory then
                        Maybe.withDefault "" (List.head cats)

                    else
                        model.uploadCategory
              }
            , Cmd.none
            )

        GotCategories (Err _) ->
            ( model, Cmd.none )

        StartEdit item ->
            ( { model | editing = Just ( item.id, editFormFromItem item ) }, Cmd.none )

        CancelEdit ->
            ( { model | editing = Nothing }, Cmd.none )

        UpdateForm updater ->
            case model.editing of
                Just ( id, form ) ->
                    ( { model | editing = Just ( id, updater form ) }, Cmd.none )

                Nothing ->
                    ( model, Cmd.none )

        SubmitImport itemId ->
            case model.editing of
                Just ( editId, form ) ->
                    if editId == itemId then
                        ( model
                        , Api.importItem itemId
                            (formToImportRequest form)
                            (GotImportResult itemId)
                        )

                    else
                        ( model, Cmd.none )

                Nothing ->
                    ( model, Cmd.none )

        GotImportResult itemId (Ok _) ->
            ( { model
                | items = List.filter (\i -> i.id /= itemId) model.items
                , editing = Nothing
              }
            , Cmd.none
            )

        GotImportResult _ (Err err) ->
            ( { model | error = Just (httpErrorToString err) }, Cmd.none )

        Discard itemId ->
            ( model, Api.discardItem itemId (GotDiscardResult itemId) )

        GotDiscardResult itemId (Ok _) ->
            ( { model | items = List.filter (\i -> i.id /= itemId) model.items }
            , Cmd.none
            )

        GotDiscardResult _ (Err err) ->
            ( { model | error = Just (httpErrorToString err) }, Cmd.none )

        PickFiles ->
            ( model
            , Select.files [ "audio/*", "application/zip", ".zip" ] GotFiles
            )

        GotFiles first rest ->
            ( { model | pendingFiles = first :: rest, uploadError = Nothing }, Cmd.none )

        SetUploadCategory cat ->
            ( { model | uploadCategory = cat }, Cmd.none )

        Upload ->
            if List.isEmpty model.pendingFiles then
                ( model, Cmd.none )

            else
                ( { model | uploading = True, uploadError = Nothing }
                , Api.uploadFiles model.uploadCategory model.pendingFiles GotUploadResult
                )

        GotUploadResult (Ok _) ->
            ( { model | uploading = False, pendingFiles = [], loading = True }
            , Api.getInbox GotItems
            )

        GotUploadResult (Err err) ->
            ( { model | uploading = False, uploadError = Just (httpErrorToString err) }
            , Cmd.none
            )

        SetFilter cat ->
            ( { model | filterCategory = cat }, Cmd.none )


-- ── View ──────────────────────────────────────────────────────────────────────


view : Model -> Html Msg
view model =
    div [ class "inbox-page" ]
        [ viewUploadSection model
        , viewFilterBar model
        , viewBody model
        ]


viewUploadSection : Model -> Html Msg
viewUploadSection model =
    div [ class "upload-section" ]
        [ h2 [] [ text "Upload files" ]
        , div [ class "upload-row" ]
            [ button
                [ onClick PickFiles
                , disabled model.uploading
                , class "btn"
                ]
                [ text
                    (if List.isEmpty model.pendingFiles then
                        "Choose files…"

                     else
                        String.fromInt (List.length model.pendingFiles)
                            ++ " file(s) selected"
                    )
                ]
            , select
                [ onInput SetUploadCategory
                , value model.uploadCategory
                , class "select"
                ]
                (List.map
                    (\cat -> option [ value cat ] [ text cat ])
                    model.categories
                )
            , button
                [ onClick Upload
                , disabled (List.isEmpty model.pendingFiles || model.uploading)
                , class "btn btn-primary"
                ]
                [ text
                    (if model.uploading then
                        "Uploading…"

                     else
                        "Upload"
                    )
                ]
            ]
        , case model.uploadError of
            Just err ->
                p [ class "error-msg" ] [ text err ]

            Nothing ->
                text ""
        ]


viewFilterBar : Model -> Html Msg
viewFilterBar model =
    div [ class "filter-bar" ]
        [ label [ class "filter-label" ] [ text "Category" ]
        , select
            [ onInput
                (\val ->
                    if val == "" then
                        SetFilter Nothing

                    else
                        SetFilter (Just val)
                )
            , class "select"
            ]
            (option [ value "" ] [ text "All" ]
                :: List.map (\cat -> option [ value cat ] [ text cat ]) model.categories
            )
        , button [ onClick Refresh, class "btn" ] [ text "↻ Refresh" ]
        ]


viewBody : Model -> Html Msg
viewBody model =
    if model.loading then
        p [ class "loading" ] [ text "Loading…" ]

    else
        case model.error of
            Just err ->
                p [ class "error-msg" ] [ text err ]

            Nothing ->
                let
                    visible =
                        case model.filterCategory of
                            Nothing ->
                                model.items

                            Just cat ->
                                List.filter (\i -> i.category == cat) model.items
                in
                if List.isEmpty visible then
                    p [ class "empty-msg" ] [ text "Inbox is empty." ]

                else
                    div [] (List.map (viewGroup model.editing) (groupByCategory visible))


viewGroup : Maybe ( String, EditForm ) -> ( String, List InboxItem ) -> Html Msg
viewGroup editing ( cat, items ) =
    div [ class "category-group" ]
        [ h2 [ class "category-heading" ] [ text cat ]
        , div [ class "item-list" ] (List.map (viewItem editing) items)
        ]


viewItem : Maybe ( String, EditForm ) -> InboxItem -> Html Msg
viewItem editing item =
    case editing of
        Just ( editId, form ) ->
            if editId == item.id then
                viewEditForm item form

            else
                viewItemRow item

        Nothing ->
            viewItemRow item


viewItemRow : InboxItem -> Html Msg
viewItemRow item =
    div [ class "item-row" ]
        [ div [ class "item-info" ]
            [ span [ class "item-name" ] [ text (displayName item) ]
            , viewTagSummary item
            ]
        , div [ class "item-actions" ]
            [ button
                [ onClick (StartEdit item), class "btn btn-primary" ]
                [ text "Edit & Import" ]
            , button
                [ onClick (Discard item.id), class "btn btn-danger" ]
                [ text "Discard" ]
            ]
        ]


viewTagSummary : InboxItem -> Html Msg
viewTagSummary item =
    let
        parts =
            List.filterMap identity
                [ Maybe.map (\v -> "artist: " ++ v) item.artist
                , Maybe.map (\v -> "album: " ++ v) item.album
                , Maybe.map (\v -> "title: " ++ v) item.title
                , Maybe.map (\v -> "year: " ++ String.fromInt v) item.year
                , Maybe.map (\v -> "uploader: " ++ v) item.uploader
                ]
    in
    if List.isEmpty parts then
        span [ class "tag-summary empty" ] [ text "no tags" ]

    else
        span [ class "tag-summary" ] [ text (String.join " · " parts) ]


viewEditForm : InboxItem -> EditForm -> Html Msg
viewEditForm item form =
    div [ class "item-edit" ]
        [ p [ class "item-name" ] [ text (displayName item) ]
        , div [ class "edit-fields" ]
            [ fieldInput "Title" form.title (\v -> UpdateForm (\f -> { f | title = v }))
            , fieldInput "Artist" form.artist (\v -> UpdateForm (\f -> { f | artist = v }))
            , fieldInput "Album" form.album (\v -> UpdateForm (\f -> { f | album = v }))
            , fieldInput "Album artist" form.albumartist (\v -> UpdateForm (\f -> { f | albumartist = v }))
            , fieldInput "Genre" form.genre (\v -> UpdateForm (\f -> { f | genre = v }))
            , fieldInput "Year" form.year (\v -> UpdateForm (\f -> { f | year = v }))
            ]
        , viewSidecarInfo item
        , div [ class "edit-actions" ]
            [ button
                [ onClick (SubmitImport item.id), class "btn btn-primary" ]
                [ text "Import" ]
            , button
                [ onClick CancelEdit, class "btn" ]
                [ text "Cancel" ]
            ]
        ]


fieldInput : String -> String -> (String -> Msg) -> Html Msg
fieldInput labelText val toMsg =
    div [ class "field" ]
        [ label [ class "field-label" ] [ text labelText ]
        , input
            [ type_ "text"
            , value val
            , onInput toMsg
            , placeholder labelText
            , class "field-input"
            ]
            []
        ]


viewSidecarInfo : InboxItem -> Html Msg
viewSidecarInfo item =
    let
        rows =
            List.filterMap identity
                [ Maybe.map (\v -> ( "Source", a [ href v, target "_blank" ] [ text v ] )) item.sourceUrl
                , Maybe.map (\v -> ( "Uploader", text v )) item.uploader
                , Maybe.map (\v -> ( "Date", text v )) item.uploadDate
                ]
    in
    if List.isEmpty rows then
        text ""

    else
        dl [ class "sidecar-info" ]
            (List.concatMap (\( k, v ) -> [ dt [] [ text k ], dd [] [ v ] ]) rows)


-- ── Helpers ───────────────────────────────────────────────────────────────────


displayName : InboxItem -> String
displayName item =
    let
        base =
            item.path
                |> String.split "/"
                |> List.reverse
                |> List.head
                |> Maybe.withDefault item.path

        prefix =
            if item.isGroup then
                "📁 "

            else
                "🎵 "
    in
    prefix ++ base


groupByCategory : List InboxItem -> List ( String, List InboxItem )
groupByCategory items =
    let
        -- Preserve insertion order of categories
        cats =
            List.foldr
                (\item acc ->
                    if List.member item.category acc then
                        acc

                    else
                        item.category :: acc
                )
                []
                items
    in
    List.map
        (\cat -> ( cat, List.filter (\i -> i.category == cat) items ))
        cats
