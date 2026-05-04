module Types exposing
    ( EditForm
    , InboxItem
    , TagUpdate
    , TrackInfo
    , editFormFromItem
    , encodeTagUpdate
    , formToTagUpdate
    , httpErrorToString
    , inboxItemDecoder
    )

import Http
import Json.Decode as D
import Json.Encode as E


-- ── Applicative helper ────────────────────────────────────────────────────────

andMap : D.Decoder a -> D.Decoder (a -> b) -> D.Decoder b
andMap =
    D.map2 (|>)


-- ── TrackInfo ─────────────────────────────────────────────────────────────────


type alias TrackInfo =
    { id : String
    , path : String
    , title : Maybe String
    , artist : Maybe String
    , albumartist : Maybe String
    , genre : Maybe String
    , year : Maybe Int
    , track : Maybe Int
    }


trackInfoDecoder : D.Decoder TrackInfo
trackInfoDecoder =
    D.succeed TrackInfo
        |> andMap (D.field "id" D.string)
        |> andMap (D.field "path" D.string)
        |> andMap (D.field "title" (D.nullable D.string))
        |> andMap (D.field "artist" (D.nullable D.string))
        |> andMap (D.field "albumartist" (D.nullable D.string))
        |> andMap (D.field "genre" (D.nullable D.string))
        |> andMap (D.field "year" (D.nullable D.int))
        |> andMap (D.field "track" (D.nullable D.int))


-- ── InboxItem ─────────────────────────────────────────────────────────────────


type alias InboxItem =
    { id : String
    , category : String
    , path : String
    , isGroup : Bool
    , files : List String
    , cataloged : Bool
    , title : Maybe String
    , artist : Maybe String
    , album : Maybe String
    , albumartist : Maybe String
    , genre : Maybe String
    , year : Maybe Int
    , track : Maybe Int
    , sourceUrl : Maybe String
    , uploader : Maybe String
    , uploadDate : Maybe String
    , tracks : List TrackInfo
    }


inboxItemDecoder : D.Decoder InboxItem
inboxItemDecoder =
    D.succeed InboxItem
        |> andMap (D.field "id" D.string)
        |> andMap (D.field "category" D.string)
        |> andMap (D.field "path" D.string)
        |> andMap (D.field "is_group" D.bool)
        |> andMap (D.field "files" (D.list D.string))
        |> andMap (D.field "cataloged" D.bool)
        |> andMap (D.field "title" (D.nullable D.string))
        |> andMap (D.field "artist" (D.nullable D.string))
        |> andMap (D.field "album" (D.nullable D.string))
        |> andMap (D.field "albumartist" (D.nullable D.string))
        |> andMap (D.field "genre" (D.nullable D.string))
        |> andMap (D.field "year" (D.nullable D.int))
        |> andMap (D.field "track" (D.nullable D.int))
        |> andMap (D.field "source_url" (D.nullable D.string))
        |> andMap (D.field "uploader" (D.nullable D.string))
        |> andMap (D.field "upload_date" (D.nullable D.string))
        |> andMap (D.field "tracks" (D.list trackInfoDecoder))


-- ── EditForm ──────────────────────────────────────────────────────────────────


type alias EditForm =
    { title : String
    , artist : String
    , album : String
    , albumartist : String
    , genre : String
    , year : String
    }


editFormFromItem : InboxItem -> EditForm
editFormFromItem item =
    { title = Maybe.withDefault "" item.title
    , artist = Maybe.withDefault "" item.artist
    , album = Maybe.withDefault "" item.album
    , albumartist = Maybe.withDefault "" item.albumartist
    , genre = Maybe.withDefault "" item.genre
    , year = Maybe.withDefault "" (Maybe.map String.fromInt item.year)
    }


-- ── TagUpdate ─────────────────────────────────────────────────────────────────


type alias TagUpdate =
    { title : Maybe String
    , artist : Maybe String
    , album : Maybe String
    , albumartist : Maybe String
    , genre : Maybe String
    , year : Maybe Int
    }


encodeTagUpdate : TagUpdate -> E.Value
encodeTagUpdate u =
    [ Maybe.map (\v -> ( "title", E.string v )) u.title
    , Maybe.map (\v -> ( "artist", E.string v )) u.artist
    , Maybe.map (\v -> ( "album", E.string v )) u.album
    , Maybe.map (\v -> ( "albumartist", E.string v )) u.albumartist
    , Maybe.map (\v -> ( "genre", E.string v )) u.genre
    , Maybe.map (\v -> ( "year", E.int v )) u.year
    ]
        |> List.filterMap identity
        |> E.object


formToTagUpdate : EditForm -> TagUpdate
formToTagUpdate form =
    { title = nonEmpty form.title
    , artist = nonEmpty form.artist
    , album = nonEmpty form.album
    , albumartist = nonEmpty form.albumartist
    , genre = nonEmpty form.genre
    , year = String.toInt form.year
    }


-- ── Shared helpers ────────────────────────────────────────────────────────────


nonEmpty : String -> Maybe String
nonEmpty s =
    let
        trimmed =
            String.trim s
    in
    if String.isEmpty trimmed then
        Nothing

    else
        Just trimmed


httpErrorToString : Http.Error -> String
httpErrorToString err =
    case err of
        Http.BadUrl url ->
            "Bad URL: " ++ url

        Http.Timeout ->
            "Request timed out"

        Http.NetworkError ->
            "Network error"

        Http.BadStatus code ->
            "Server error: " ++ String.fromInt code

        Http.BadBody body ->
            "Bad response: " ++ body
