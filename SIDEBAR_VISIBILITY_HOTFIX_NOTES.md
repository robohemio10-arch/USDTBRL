# Sidebar visibility hotfix

- fixed left sidebar clipping on Streamlit by forcing the sidebar container and its inner wrapper to stay at `left: 0`
- removed residual horizontal offset/transform that left half the sidebar outside the viewport
- preserved the fixed-width sidebar layout and the operational buttons
