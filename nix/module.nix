{ config, lib, pkgs, ... }:

let
  cfg = config.services.beets-inbox;
in
{
  options.services.beets-inbox = {
    enable = lib.mkEnableOption "beets-inbox music inbox service";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The beets-inbox package to use.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8085;
      description = "Port the HTTP server listens on.";
    };

    inboxPath = lib.mkOption {
      type = lib.types.str;
      description = "Path to the inbox directory (where uploaded music lands).";
      example = "/var/lib/beets-inbox/inbox";
    };

    dataPath = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/beets-inbox/data";
      description = "Path for beets-inbox state (beets DB, generated configs).";
    };

    libraryPath = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Path to the main beets music library. Null = no main library configured.";
      example = "/media/music";
    };

    defaultCategory = lib.mkOption {
      type = lib.types.str;
      default = "unsorted";
      description = "Default inbox category for uploads without an explicit category.";
    };

    autotag = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Whether beets queries MusicBrainz when cataloging uploaded files.";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "beets-inbox";
      description = "User account under which the service runs.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "beets-inbox";
      description = "Group under which the service runs.";
    };

    extraEnvironment = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = {};
      description = "Extra environment variables passed to the service.";
      example = { BEETS_AUTOTAG = "false"; };
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = lib.mkIf (cfg.user == "beets-inbox") {
      isSystemUser = true;
      group = cfg.group;
      description = "beets-inbox service user";
    };

    users.groups.${cfg.group} = lib.mkIf (cfg.group == "beets-inbox") {};

    systemd.services.beets-inbox = {
      description = "beets-inbox music inbox";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        ExecStart = "${cfg.package}/bin/beets-inbox";
        Restart = "on-failure";
        RestartSec = "5s";

        # State directories
        StateDirectory = "beets-inbox";
        StateDirectoryMode = "0750";

        # Hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = lib.flatten [
          cfg.inboxPath
          cfg.dataPath
          (lib.optional (cfg.libraryPath != null) cfg.libraryPath)
        ];
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectControlGroups = true;
      };

      environment = lib.mkMerge [
        {
          BEETS_INBOX_PATH = cfg.inboxPath;
          BEETS_DATA_PATH = cfg.dataPath;
          BEETS_DEFAULT_CATEGORY = cfg.defaultCategory;
          BEETS_INBOX_PORT = toString cfg.port;
          BEETS_AUTOTAG = if cfg.autotag then "true" else "false";
          BEETS_STATIC_DIR = "${cfg.package}/share/beets-inbox/frontend";
          # beets (via confuse) tries to create $HOME/.config even when
          # --config is passed explicitly; point HOME at the writable data dir.
          HOME = cfg.dataPath;
        }
        (lib.optionalAttrs (cfg.libraryPath != null) {
          BEETS_LIBRARY_PATH = cfg.libraryPath;
        })
        cfg.extraEnvironment
      ];
    };

    # Ensure inbox directory exists with correct ownership
    systemd.tmpfiles.rules = [
      "d '${cfg.inboxPath}' 0750 ${cfg.user} ${cfg.group} - -"
      "d '${cfg.dataPath}' 0750 ${cfg.user} ${cfg.group} - -"
    ];
  };
}
