module Api exposing
    ( discardItem
    , getCategories
    , getInbox
    , getJob
    , getJobs
    , importItem
    , uploadFiles
    )

import File exposing (File)
import Http
import Json.Decode as D
import Types exposing (..)


base : String
base =
    "/api"


getInbox : (Result Http.Error (List InboxItem) -> msg) -> Cmd msg
getInbox toMsg =
    Http.get
        { url = base ++ "/inbox"
        , expect = Http.expectJson toMsg (D.list inboxItemDecoder)
        }


getCategories : (Result Http.Error (List String) -> msg) -> Cmd msg
getCategories toMsg =
    Http.get
        { url = base ++ "/inbox/categories"
        , expect = Http.expectJson toMsg (D.list D.string)
        }


importItem : String -> ImportRequest -> (Result Http.Error Job -> msg) -> Cmd msg
importItem itemId req toMsg =
    Http.post
        { url = base ++ "/inbox/" ++ itemId ++ "/import"
        , body = Http.jsonBody (encodeImportRequest req)
        , expect = Http.expectJson toMsg jobDecoder
        }


discardItem : String -> (Result Http.Error () -> msg) -> Cmd msg
discardItem itemId toMsg =
    Http.request
        { method = "DELETE"
        , headers = []
        , url = base ++ "/inbox/" ++ itemId
        , body = Http.emptyBody
        , expect = Http.expectWhatever toMsg
        , timeout = Nothing
        , tracker = Nothing
        }


uploadFiles : String -> Bool -> List File -> (Result Http.Error () -> msg) -> Cmd msg
uploadFiles category autotag files toMsg =
    let
        params =
            List.filterMap identity
                [ if String.isEmpty (String.trim category) then
                    Nothing

                  else
                    Just ("category=" ++ category)
                , Just
                    (if autotag then
                        "autotag=true"

                     else
                        "autotag=false"
                    )
                ]

        url =
            if List.isEmpty params then
                base ++ "/inbox/upload"

            else
                base ++ "/inbox/upload?" ++ String.join "&" params
    in
    Http.request
        { method = "POST"
        , headers = []
        , url = url
        , body = Http.multipartBody (List.map (Http.filePart "files") files)
        , expect = Http.expectWhatever toMsg
        , timeout = Nothing
        , tracker = Nothing
        }


getJobs : (Result Http.Error (List Job) -> msg) -> Cmd msg
getJobs toMsg =
    Http.get
        { url = base ++ "/jobs"
        , expect = Http.expectJson toMsg (D.list jobDecoder)
        }


getJob : String -> (Result Http.Error Job -> msg) -> Cmd msg
getJob jobId toMsg =
    Http.get
        { url = base ++ "/jobs/" ++ jobId
        , expect = Http.expectJson toMsg jobDecoder
        }
