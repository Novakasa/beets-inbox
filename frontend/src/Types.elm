module Types exposing
    ( EditForm
    , ImportRequest
    , InboxItem
    , Job
    , JobStatus(..)
    , editFormFromItem
    , encodeImportRequest
    , formToImportRequest
    , httpErrorToString
    , inboxItemDecoder
    , jobDecoder
    , jobStatusLabel
    )

import Http
import Json.Decode as D
import Json.Encode as E


-- ── Applicative helper ────────────────────────────────────────────────────────
-- Lets us decode records with more than 8 fields without external packages.

andMap : D.Decoder a -> D.Decoder (a -> b) -> D.Decoder b
andMap =
    D.map2 (|>)


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


-- ── EditForm ──────────────────────────────────────────────────────────────────


type alias EditForm =
    { title : String
    , artist : String
    , album : String
    , albumartist : String
    , genre : String
    , year : String -- String input; parsed to Int on submit
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


-- ── ImportRequest ─────────────────────────────────────────────────────────────


type alias ImportRequest =
    { title : Maybe String
    , artist : Maybe String
    , album : Maybe String
    , albumartist : Maybe String
    , genre : Maybe String
    , year : Maybe Int
    }


formToImportRequest : EditForm -> ImportRequest
formToImportRequest form =
    { title = nonEmpty form.title
    , artist = nonEmpty form.artist
    , album = nonEmpty form.album
    , albumartist = nonEmpty form.albumartist
    , genre = nonEmpty form.genre
    , year = String.toInt form.year
    }


encodeImportRequest : ImportRequest -> E.Value
encodeImportRequest req =
    [ Maybe.map (\v -> ( "title", E.string v )) req.title
    , Maybe.map (\v -> ( "artist", E.string v )) req.artist
    , Maybe.map (\v -> ( "album", E.string v )) req.album
    , Maybe.map (\v -> ( "albumartist", E.string v )) req.albumartist
    , Maybe.map (\v -> ( "genre", E.string v )) req.genre
    , Maybe.map (\v -> ( "year", E.int v )) req.year
    ]
        |> List.filterMap identity
        |> E.object


-- ── Job ───────────────────────────────────────────────────────────────────────


type JobStatus
    = Pending
    | Running
    | Success
    | Failed


type alias Job =
    { id : String
    , status : JobStatus
    , sourcePath : String
    , category : Maybe String
    , artist : Maybe String
    , album : Maybe String
    , genre : Maybe String
    , log : String
    , createdAt : String
    , completedAt : Maybe String
    }


jobStatusDecoder : D.Decoder JobStatus
jobStatusDecoder =
    D.string
        |> D.andThen
            (\s ->
                case s of
                    "pending" ->
                        D.succeed Pending

                    "running" ->
                        D.succeed Running

                    "success" ->
                        D.succeed Success

                    "failed" ->
                        D.succeed Failed

                    _ ->
                        D.fail ("Unknown job status: " ++ s)
            )


jobDecoder : D.Decoder Job
jobDecoder =
    D.succeed Job
        |> andMap (D.field "id" D.string)
        |> andMap (D.field "status" jobStatusDecoder)
        |> andMap (D.field "source_path" D.string)
        |> andMap (D.field "category" (D.nullable D.string))
        |> andMap (D.field "artist" (D.nullable D.string))
        |> andMap (D.field "album" (D.nullable D.string))
        |> andMap (D.field "genre" (D.nullable D.string))
        |> andMap (D.field "log" D.string)
        |> andMap (D.field "created_at" D.string)
        |> andMap (D.field "completed_at" (D.nullable D.string))


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


jobStatusLabel : JobStatus -> String
jobStatusLabel status =
    case status of
        Pending ->
            "pending"

        Running ->
            "running"

        Success ->
            "success"

        Failed ->
            "failed"


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
