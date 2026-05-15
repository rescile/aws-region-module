{
  description = "AWS Deployment Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      system = "x86_64-linux"; # Adjust to "aarch64-darwin" for Apple Silicon
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        # 1. Packages to stay in the PATH
        buildInputs = [
          pkgs.awscli2
          (pkgs.python3.withPackages (ps: [
            ps.boto3
            ps.botocore
          ]))
        ];

        # 2. Automation: Set environment variables or aliases upon entry
        shellHook = ''
          echo "☁️  AWS Python SDK Loaded"
          echo "Python version: $(python --version)"
          export AWS_DEFAULT_REGION="us-east-1"
          # Optional: Create a local venv if you need to pip install extra things
          if [ ! -d ".venv" ]; then
            python -m venv .venv
          fi
        '';
      };
    };
}
