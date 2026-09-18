{ printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize"}'
  sleep 7; printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
} | npx -y mcp-remote "https://mcp.exa.ai/mcp" 2>/dev/null
